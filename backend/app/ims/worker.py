"""
worker.py — Fixed for Windows ProactorEventLoop destructor bug.

ROOT CAUSE OF "Event loop is closed" ON WINDOWS:
  asyncio on Windows 3.8+ defaults to ProactorEventLoop.
  asyncpg and Motor open TCP connections via this loop.
  When asyncio.run() calls loop.close(), pending transport
  destructors try to call loop.call_soon() AFTER close —
  raising RuntimeError: Event loop is closed.

FIX:
  Force SelectorEventLoop on Windows before any asyncio.run() call.
  SelectorEventLoop does not have this destructor-timing bug.
  asyncpg, Motor, and redis.asyncio all work correctly with it.
"""

import sys
import asyncio

# ── Windows fix: must be set BEFORE any event loop is created ──────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ───────────────────────────────────────────────────────────────────────────

import json
import traceback
from datetime import datetime

from celery import Celery
from celery.signals import task_failure

from .config import settings
from .state_machine import WorkItem, Status
from .alerting import AlertRouter, Alert


# ---------------------------------------------------------------------------
# Celery app — sync config only, no async resources at module level
# ---------------------------------------------------------------------------

celery_app = Celery(
    'ims',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,  # suppress Celery 6.0 deprecation warning
)

# Pure Python, no async init — safe at module level
alert_router = AlertRouter()


# ---------------------------------------------------------------------------
# Celery task — sync entry point
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, name="ims.worker.process_signal")
def process_signal(self, signal_data: dict):
    """
    Windows-safe async task execution.

    SelectorEventLoopPolicy is set at module level above.
    asyncio.run() creates a fresh SelectorEventLoop per task,
    runs to completion, closes cleanly without destructor race.
    """
    try:
        print(f"🔥 TASK STARTED | component={signal_data.get('component_id')} severity={signal_data.get('severity')}")
        result = asyncio.run(_process_signal_async(signal_data))
        print(f"✅ TASK COMPLETED | {result}")
        return result

    except Exception as exc:
        print(f"❌ TASK FAILED | attempt {self.request.retries + 1}/3")
        print(traceback.format_exc())  # full stack, not just str(exc)
        countdown = 5 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


# ---------------------------------------------------------------------------
# Async implementation — all clients created inside the running loop
# ---------------------------------------------------------------------------

async def _process_signal_async(signal_data: dict) -> dict:
    """
    Every async resource is created here, inside the fresh SelectorEventLoop.
    Explicit cleanup in finally ensures everything closes BEFORE
    asyncio.run() calls loop.close() — preventing the destructor race.
    """
    import redis.asyncio as aioredis
    from motor.motor_asyncio import AsyncIOMotorClient
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from .persistence import WorkItemRepository, SignalRepository
    from .debouncer import SignalDebouncer

    component_id = signal_data['component_id']
    severity = signal_data['severity']

    # All clients bound to THIS loop's SelectorEventLoop
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    engine = create_async_engine(
        settings.postgres_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # 1. Debounce via Redis ZSET
        debouncer = SignalDebouncer(
            window_seconds=settings.debounce_window_seconds,
            redis_client=redis_client,
        )
        signal_json = json.dumps(signal_data, default=str).encode()
        is_new, work_item_id = await debouncer.process(component_id, signal_json)

        # 2. Store raw signal in MongoDB
        db = mongo_client.get_database()
        await db.raw_signals.insert_one({
            "work_item_id": work_item_id,
            "component_id": component_id,
            "payload": signal_data,
            "ingested_at": datetime.utcnow(),
        })

        if is_new:
            # 3. Create WorkItem in PostgreSQL
            async with SessionLocal() as session:
                work_item = WorkItem(
                    id=work_item_id,
                    component_id=component_id,
                    severity=severity,
                )
                await WorkItemRepository.create(session, work_item)

            # 4. Update Redis dashboard cache
            await redis_client.zadd(
                f"dashboard:active:{severity}",
                {work_item_id: datetime.utcnow().timestamp()},
            )
            await redis_client.publish("dashboard:updates", work_item_id)

            # 5. Dispatch alert (Strategy Pattern)
            alert = Alert(
                work_item_id=work_item_id,
                component_id=component_id,
                severity=severity,
                message=f"New incident detected: {component_id}",
            )
            await alert_router.dispatch(alert)

            return {"status": "processed", "work_item_id": work_item_id, "is_new": True}

        return {"status": "debounced", "work_item_id": work_item_id, "is_new": False}

    finally:
        # CRITICAL: explicit cleanup BEFORE asyncio.run() closes the loop.
        # Each in its own try/except so one failure doesn't skip the others.
        try:
            await redis_client.aclose()
        except Exception:
            pass
        try:
            mongo_client.close()
        except Exception:
            pass
        try:
            await engine.dispose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Global failure signal
# ---------------------------------------------------------------------------

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    print(f"🔥 [WORKER FINAL FAILURE] task_id={task_id} | {type(exception).__name__}: {exception}")
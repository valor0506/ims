"""
main.py — Fixed:
1. /ingest now returns 202 Accepted (was 200 — load tester was always seeing 0 accepted)
2. queue_depth missing await on async redis call
3. Two @on_event("startup") merged into lifespan (on_event is deprecated)
4. on_event deprecation warnings removed
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import time
import asyncio

from .config import settings
from .database import init_db, get_db, engine
from .mongo_client import init_mongo_indexes
from .redis_client import init_redis, redis_client
from .state_machine import WorkItem, Status, RCA, InvalidTransition, RCARequired
from .persistence import WorkItemRepository, SignalRepository
from .alerting import AlertRouter, Alert
from .worker import celery_app
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Metrics (in-memory, reset every 5s by reporter)
# ---------------------------------------------------------------------------

metrics = {
    "signals_received": 0,
    "signals_dropped": 0,
    "last_metrics_time": time.time()
}

# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup"/"shutdown")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Single startup/shutdown handler. Replaces @on_event (deprecated)."""

    # ── Startup ──────────────────────────────────────────────────────────
    await init_db()
    await init_mongo_indexes()
    await init_redis()
    print("✅ All services initialized")

    # Start background metrics reporter as a non-blocking task
    reporter_task = asyncio.create_task(_metrics_reporter())

    yield  # app runs here

    # ── Shutdown ─────────────────────────────────────────────────────────
    reporter_task.cancel()
    await engine.dispose()
    print("✅ Shutdown complete")


async def _metrics_reporter():
    """Logs throughput every 5 seconds."""
    while True:
        await asyncio.sleep(5)
        now = time.time()
        elapsed = now - metrics["last_metrics_time"]
        throughput = metrics["signals_received"] / elapsed if elapsed > 0 else 0

        # Correct: await the async redis call
        try:
            queue_depth = await redis_client.llen("celery")
        except Exception:
            queue_depth = "unavailable"

        print(
            f"[METRICS] Signals/sec: {throughput:.0f} | "
            f"Received: {metrics['signals_received']} | "
            f"Dropped: {metrics['signals_dropped']} | "
            f"Queue depth: {queue_depth}"
        )
        metrics["signals_received"] = 0
        metrics["signals_dropped"] = 0
        metrics["last_metrics_time"] = now


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Incident Management System",
    description="Mission-critical incident management with async processing",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SignalIngest(BaseModel):
    component_id: str = Field(..., min_length=1, max_length=100)
    severity: str = Field(..., pattern="^(P0|P1|P2|P3)$")
    payload: Dict[str, Any]
    timestamp: Optional[datetime] = None

class RCASubmission(BaseModel):
    start_time: datetime
    end_time: datetime
    root_cause_category: str = Field(..., pattern="^(infra|code|config|dependency)$")
    fix_applied: str = Field(..., min_length=20)
    prevention_steps: str = Field(..., min_length=20)

class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(OPEN|INVESTIGATING|RESOLVED|CLOSED)$")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"

    try:
        from .mongo_client import mongo_client
        await mongo_client.admin.command('ping')
        mongo_status = "connected"
    except Exception as e:
        mongo_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "services": {
            "redis": redis_status,
            "mongodb": mongo_status,
            "postgres": "connected",
        },
        "metrics": {
            "signals_received": metrics["signals_received"],
            "signals_dropped": metrics["signals_dropped"],
        }
    }


@app.post("/ingest", status_code=202)   # ← 202 Accepted, not 200
async def ingest_signal(signal: SignalIngest):
    """
    Enqueue signal to Celery and return 202 immediately.
    The load tester checks for 202 — without this it always reports 0 accepted.
    """
    signal_dict = {
        "component_id": signal.component_id,
        "severity": signal.severity,
        "payload": signal.payload,
        "timestamp": signal.timestamp.isoformat() if signal.timestamp else datetime.utcnow().isoformat()
    }

    try:
        from .worker import process_signal
        process_signal.delay(signal_dict)
        metrics["signals_received"] += 1
        return {
            "status": "accepted",
            "component_id": signal.component_id,
            "severity": signal.severity,
        }
    except Exception as e:
        metrics["signals_dropped"] += 1
        raise HTTPException(status_code=503, detail=f"Failed to enqueue: {str(e)}")


@app.get("/incidents/active")
async def get_active_incidents(db: AsyncSession = Depends(get_db)):
    work_items = await WorkItemRepository.get_active(db)
    return [wi.to_dict() for wi in work_items]


@app.get("/incidents/{work_item_id}")
async def get_incident(work_item_id: str, db: AsyncSession = Depends(get_db)):
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")

    signals = await SignalRepository.get_by_work_item(work_item_id)

    return {
        "work_item": work_item.to_dict(),
        "signals": signals,
        "signal_count": len(signals),
    }


@app.post("/incidents/{work_item_id}/rca")
async def submit_rca(
    work_item_id: str,
    rca_data: RCASubmission,
    db: AsyncSession = Depends(get_db)
):
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")

    work_item.rca = RCA(
        start_time=rca_data.start_time,
        end_time=rca_data.end_time,
        root_cause_category=rca_data.root_cause_category,
        fix_applied=rca_data.fix_applied,
        prevention_steps=rca_data.prevention_steps,
    )

    await WorkItemRepository.update(db, work_item)

    return {
        "status": "rca_submitted",
        "work_item_id": work_item_id,
        "rca": {
            "start_time": work_item.rca.start_time.isoformat(),
            "end_time": work_item.rca.end_time.isoformat(),
            "root_cause_category": work_item.rca.root_cause_category,
            "fix_applied": work_item.rca.fix_applied,
            "prevention_steps": work_item.rca.prevention_steps,
        }
    }


@app.patch("/incidents/{work_item_id}/status")
async def update_status(
    work_item_id: str,
    update: StatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")

    try:
        new_status = Status(update.status)
        work_item.transition_to(new_status)
        await WorkItemRepository.update(db, work_item)

        if new_status == Status.CLOSED:
            await redis_client.zrem(f"dashboard:active:{work_item.severity}", work_item_id)
            await redis_client.publish("dashboard:updates", work_item_id)

        return {
            "status": "updated",
            "work_item_id": work_item_id,
            "new_status": work_item.status.value,
            "mttr_seconds": work_item.mttr_seconds,
        }

    except InvalidTransition as e:
        raise HTTPException(400, detail=str(e))
    except RCARequired as e:
        raise HTTPException(400, detail=str(e))


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

from .websocket import dashboard_websocket

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await dashboard_websocket(websocket)
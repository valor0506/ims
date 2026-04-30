from celery import Celery
from celery.signals import task_failure
import asyncio
import json
from datetime import datetime

from .config import settings
from .debouncer import SignalDebouncer
from .state_machine import WorkItem, Status
from .alerting import AlertRouter, Alert
from .persistence import WorkItemRepository, SignalRepository
from .database import AsyncSessionLocal
from .redis_client import redis_client

# Celery app configuration
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
    task_time_limit=30,  # Kill task after 30 seconds
    worker_prefetch_multiplier=1,  # Don't prefetch if tasks are slow (fairness)
    worker_max_tasks_per_child=1000,  # Restart worker to prevent memory leaks
)

# Initialize components
debouncer = SignalDebouncer(window_seconds=settings.debounce_window_seconds)
alert_router = AlertRouter()

@celery_app.task(bind=True, max_retries=3)
def process_signal(self, signal_data: dict):
    """
    Celery task: Process ingested signal.
    
    Flow:
    1. Debounce (check if work item exists for component)
    2. Store raw signal in MongoDB
    3. If new work item: create in Postgres, update cache, dispatch alert
    """
    try:
        # Run async code inside Celery (which is sync)
        asyncio.run(_process_signal_async(signal_data))
        return {"status": "processed"}
        
    except Exception as exc:
        # Retry with exponential backoff: 5s, 10s, 20s
        countdown = 5 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)

async def _process_signal_async(signal_data: dict):
    """Async implementation of signal processing"""
    component_id = signal_data['component_id']
    severity = signal_data['severity']
    
    # Serialize signal for debouncer (expects bytes)
    signal_json = json.dumps(signal_data).encode()
    
    # 1. Debounce: check sliding window
    is_new, work_item_id = await debouncer.process(component_id, signal_json)
    
    # 2. Store raw signal in MongoDB (Data Lake)
    await SignalRepository.store({
        "work_item_id": work_item_id,
        "component_id": component_id,
        "payload": signal_data,
        "ingested_at": datetime.utcnow()
    })
    
    if is_new:
        # 3. Create Work Item in PostgreSQL (Source of Truth)
        async with AsyncSessionLocal() as session:
            work_item = WorkItem(
                id=work_item_id,
                component_id=component_id,
                severity=severity
            )
            await WorkItemRepository.create(session, work_item)
            
            # 4. Update Redis cache for dashboard
            await _update_dashboard_cache(work_item)
            
            # 5. Dispatch alert based on severity (Strategy Pattern)
            alert = Alert(
                work_item_id=work_item_id,
                component_id=component_id,
                severity=severity,
                message=f"New incident detected: {component_id}"
            )
            await alert_router.dispatch(alert)

async def _update_dashboard_cache(work_item: WorkItem):
    """Update Redis sorted sets for real-time dashboard"""
    # Add to active incidents by severity
    await redis_client.zadd(
        f"dashboard:active:{work_item.severity}",
        {work_item.id: work_item.created_at.timestamp()}
    )
    
    # Publish update for WebSocket subscribers
    await redis_client.publish("dashboard:updates", work_item.id)

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Global task failure handler"""
    print(f"🔥 [WORKER ERROR] Task {task_id} failed: {exception}")
    # In production: send to Sentry, Datadog, etc.
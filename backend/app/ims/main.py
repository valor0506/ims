from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import time

from .config import settings
from .database import init_db, get_db, engine
from .mongo_client import init_mongo_indexes
from .redis_client import init_redis, redis_client
from .state_machine import WorkItem, Status, RCA, InvalidTransition, RCARequired
from .persistence import WorkItemRepository, SignalRepository
from .alerting import AlertRouter, Alert
from .worker import celery_app
from sqlalchemy.ext.asyncio import AsyncSession



app = FastAPI(
    title="Incident Management System",
    description="Mission-critical incident management with async processing",
    version="1.0.0"
)



# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics
metrics = {
    "signals_received": 0,
    "signals_dropped": 0,
    "last_metrics_time": time.time()
}

class SignalIngest(BaseModel):
    """Request model for signal ingestion"""
    component_id: str = Field(..., min_length=1, max_length=100)
    severity: str = Field(..., pattern="^(P0|P1|P2|P3)$")
    payload: Dict[str, Any]
    timestamp: Optional[datetime] = None

class RCASubmission(BaseModel):
    """Request model for RCA submission"""
    start_time: datetime
    end_time: datetime
    root_cause_category: str = Field(..., pattern="^(infra|code|config|dependency)$")
    fix_applied: str = Field(..., min_length=20)
    prevention_steps: str = Field(..., min_length=20)

class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(OPEN|INVESTIGATING|RESOLVED|CLOSED)$")

@app.on_event("startup")
async def startup():
    """Initialize all connections on startup"""
    await init_db()
    await init_mongo_indexes()
    await init_redis()
    print("✅ All services initialized")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    await engine.dispose()

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Check Redis
        await redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    try:
        # Check MongoDB
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
            "postgres": "connected"  # If we got here, it's connected
        },
        "metrics": {
            "signals_received": metrics["signals_received"],
            "signals_dropped": metrics["signals_dropped"]
        }
    }

@app.post("/ingest")
async def ingest_signal(signal: SignalIngest):
    """
    High-throughput signal ingestion endpoint.
    
    Flow:
    1. Validate request
    2. Enqueue to Celery for async processing
    3. Return 202 Accepted immediately
    """
    # Use orjson for fast serialization
    signal_dict = json.loads(json.dumps({
        "component_id": signal.component_id,
        "severity": signal.severity,
        "payload": signal.payload,
        "timestamp": signal.timestamp.isoformat() if signal.timestamp else datetime.utcnow().isoformat()
    }))
    
    # Enqueue to Celery (non-blocking)
    try:
        celery_app.send_task('ims.worker.process_signal', args=[signal_dict])
        metrics["signals_received"] += 1
        return {
            "status": "accepted",
            "component_id": signal.component_id,
            "severity": signal.severity
        }
    except Exception as e:
        metrics["signals_dropped"] += 1
        raise HTTPException(status_code=503, detail=f"Failed to enqueue: {str(e)}")

@app.get("/incidents/active")
async def get_active_incidents(db: AsyncSession = Depends(get_db)):
    """Get all active (non-closed) incidents from database"""
    work_items = await WorkItemRepository.get_active(db)
    return [wi.to_dict() for wi in work_items]

@app.get("/incidents/{work_item_id}")
async def get_incident(work_item_id: str, db: AsyncSession = Depends(get_db)):
    """Get incident details with raw signals"""
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")
    
    signals = await SignalRepository.get_by_work_item(work_item_id)
    
    return {
        "work_item": work_item.to_dict(),
        "signals": signals,
        "signal_count": len(signals)
    }

@app.post("/incidents/{work_item_id}/rca")
async def submit_rca(
    work_item_id: str,
    rca_data: RCASubmission,
    db: AsyncSession = Depends(get_db)
):
    """Submit RCA for a work item"""
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")
    
    # Create RCA object
    work_item.rca = RCA(
        start_time=rca_data.start_time,
        end_time=rca_data.end_time,
        root_cause_category=rca_data.root_cause_category,
        fix_applied=rca_data.fix_applied,
        prevention_steps=rca_data.prevention_steps
    )
    
    await WorkItemRepository.update(db, work_item)
    
    return {
        "status": "rca_submitted",
        "work_item_id": work_item_id,
        "rca": work_item.rca.to_dict() if hasattr(work_item.rca, 'to_dict') else str(work_item.rca)
    }

@app.patch("/incidents/{work_item_id}/status")
async def update_status(
    work_item_id: str,
    update: StatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update work item status with state machine validation"""
    work_item = await WorkItemRepository.get_by_id(db, work_item_id)
    if not work_item:
        raise HTTPException(404, detail="Work item not found")
    
    try:
        new_status = Status(update.status)
        work_item.transition_to(new_status)
        await WorkItemRepository.update(db, work_item)
        
        # Update dashboard cache if closed
        if new_status == Status.CLOSED:
            await redis_client.zrem(f"dashboard:active:{work_item.severity}", work_item_id)
            await redis_client.publish("dashboard:updates", work_item_id)
        
        return {
            "status": "updated",
            "work_item_id": work_item_id,
            "new_status": work_item.status.value,
            "mttr_seconds": work_item.mttr_seconds
        }
        
    except InvalidTransition as e:
        raise HTTPException(400, detail=str(e))
    except RCARequired as e:
        raise HTTPException(400, detail=str(e))

# Background metrics reporter
@app.on_event("startup")
async def start_metrics_reporter():
    import asyncio
    async def reporter():
        while True:
            await asyncio.sleep(5)
            now = time.time()
            elapsed = now - metrics["last_metrics_time"]
            throughput = metrics["signals_received"] / elapsed if elapsed > 0 else 0
            
            # Get queue depth from Celery
            try:
                queue_depth = redis_client.llen("celery")
            except:
                queue_depth = 0
            
            print(f"[METRICS] Signals/sec: {throughput:.0f} | Received: {metrics['signals_received']} | Dropped: {metrics['signals_dropped']}")
            metrics["signals_received"] = 0
            metrics["signals_dropped"] = 0
            metrics["last_metrics_time"] = now
    
    asyncio.create_task(reporter())

from .websocket import dashboard_websocket

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await dashboard_websocket(websocket)

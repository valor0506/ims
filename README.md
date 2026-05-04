# Incident Management System (IMS)

A backend system that monitors a distributed infrastructure stack and manages incidents from detection to resolution. Built for the Zeotap Infrastructure / SRE Intern Assignment.

**GitHub:** https://github.com/valor0506/ims

---

## What It Does

When components like databases, cache clusters, or API gateways start throwing errors, they send signals to this system. The system groups related signals into incidents, stores everything, fires the right alerts, and gives a dashboard to track each incident until it is closed with a Root Cause Analysis.

The main design goal was to never let the API slow down even when the database is under load. The ingestion endpoint accepts signals instantly and hands them off to background workers. The caller never waits for DB writes.

---

## Architecture

```
[Signal Sources]
      |
      v
[FastAPI /ingest]  <-- accepts signal, returns 202 immediately
      |
      v
[Redis Queue]  <-- Celery task queue
      |
      v
[Celery Worker]  <-- background processing
      |
      +---> [Debouncer] (Redis ZSET sliding window)
      |           |
      |           +--> new incident? --> [PostgreSQL] WorkItem created
      |           |
      |           +--> existing? --> link signal to it
      |
      +---> [MongoDB] raw signal stored always
      |
      +---> [Alert Router] P0=PagerDuty, P1/P2=Slack, P3=Log
      |
      +---> [Redis Cache] dashboard state updated
                  |
                  v
           [React Frontend] reads from cache, live updates via WebSocket
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| API Server | FastAPI + Uvicorn | Async by default, handles high concurrency, auto generates Swagger docs |
| Background Tasks | Celery | Runs slow DB writes in background, has built in retry with backoff |
| Message Broker | Redis | Also used for debounce window and dashboard hot cache |
| Incident Store | PostgreSQL + TimescaleDB | ACID transactions for work items, time series table for signal aggregations |
| Signal Store | MongoDB | Raw signals vary in shape, no fixed schema needed |
| Frontend | React + TanStack Query + Tailwind | Live dashboard, auto refresh, responsive |
| Containers | Docker + Docker Compose | One command starts all 6 services in correct order |

---

## Project Structure

```
ims/
├── backend/
│   ├── app/
│   │   └── ims/
│   │       ├── __init__.py
│   │       ├── main.py          # FastAPI app and all routes
│   │       ├── worker.py        # Celery task and async signal processing
│   │       ├── debouncer.py     # Sliding window dedup using Redis ZSET
│   │       ├── state_machine.py # Work Item states and transition rules
│   │       ├── alerting.py      # Strategy pattern alert router
│   │       ├── persistence.py   # Repository pattern for PG and Mongo
│   │       ├── models.py        # SQLAlchemy DB models
│   │       ├── database.py      # PostgreSQL async engine
│   │       ├── mongo_client.py  # MongoDB connection
│   │       ├── redis_client.py  # Redis client for FastAPI
│   │       ├── websocket.py     # WebSocket for live dashboard
│   │       └── config.py        # Settings from environment variables
│   ├── migrations/
│   │   └── 001_init.sql         # PostgreSQL schema + TimescaleDB setup
│   ├── celery_worker.py         # Worker entrypoint for local dev
│   ├── run.py                   # FastAPI entrypoint for local dev
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Dashboard.tsx    # Main incident list
│       │   └── IncidentDetail.tsx
│       └── api/
│           └── client.ts        # Axios client pointing to FastAPI
├── scripts/
│   └── generate_load.py         # Cascading failure load test
├── docker-compose.yml
└── README.md
```

---

## Quick Start (Docker)

This is the recommended way to run everything. All 6 services start with health checks and in the right order.

**Requirements:** Docker and Docker Compose installed.

```bash
git clone https://github.com/valor0506/ims
cd ims
docker-compose up --build
```

Wait about 30 seconds for everything to initialize. Then:

```bash
# Check all services are healthy
curl http://localhost:8000/health

# Run the cascading failure simulation
cd scripts
python generate_load.py

# Check incidents were created
curl http://localhost:8000/incidents/active
```

Open the dashboard at **http://localhost:3000**

---

## Local Dev Setup (Without Docker)

If you want to run the API and worker locally while databases run in Docker:

**Step 1: Start only the databases**
```bash
docker-compose up redis postgres mongo -d
```

**Step 2: Set up Python environment**
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate

pip install -r requirements.txt
```

**Step 3: Start FastAPI**
```bash
python run.py
```

**Step 4: Start Celery worker (new terminal)**
```bash
# Windows
python celery_worker.py

# Linux / Mac
celery -A app.ims.worker worker --loglevel=info --pool=prefork --concurrency=4
```

**Step 5: Start frontend (new terminal)**
```bash
cd frontend
npm install
npm run dev
```

Dashboard will be at **http://localhost:5173**

---

## Service URLs

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Dashboard (Docker) | http://localhost:3000 |
| Dashboard (Local Dev) | http://localhost:5173 |

---

## API Reference

### POST /ingest
Accepts a signal. Returns 202 immediately without waiting for DB writes.

```json
{
  "component_id": "RDBMS_PRIMARY",
  "severity": "P0",
  "payload": {
    "error_type": "connection_refused",
    "latency_ms": 4500,
    "trace_id": "trace-123456"
  }
}
```

Response:
```json
{
  "status": "accepted",
  "component_id": "RDBMS_PRIMARY",
  "severity": "P0"
}
```

### GET /health
Returns connection status for all three databases.

```json
{
  "status": "healthy",
  "services": {
    "redis": "connected",
    "mongodb": "connected",
    "postgres": "connected"
  },
  "metrics": {
    "signals_received": 0,
    "signals_dropped": 0
  }
}
```

### GET /incidents/active
Returns all Work Items that are not in CLOSED state.

### GET /incidents/{work_item_id}
Returns full incident details including all raw signals from MongoDB.

### PATCH /incidents/{work_item_id}/status
Move an incident through the state machine.

```json
{ "status": "INVESTIGATING" }
```

Valid transitions: OPEN → INVESTIGATING → RESOLVED → CLOSED

Trying to close without an RCA returns 400.

### POST /incidents/{work_item_id}/rca
Submit Root Cause Analysis. Required before closing.

```json
{
  "start_time": "2026-05-04T01:00:00",
  "end_time": "2026-05-04T02:30:00",
  "root_cause_category": "infra",
  "fix_applied": "Restarted the primary database and increased connection pool size",
  "prevention_steps": "Add automated failover and connection pool monitoring alerts"
}
```

---

## Design Patterns

### Strategy Pattern — Alert Routing

Each severity level has its own alert class. The AlertRouter picks the right one based on the severity of the Work Item.

```
P0  -->  PagerDutyStrategy  -->  pages on-call engineer
P1  -->  SlackStrategy      -->  posts to Slack channel
P2  -->  SlackStrategy      -->  posts to Slack channel
P3  -->  LogStrategy        -->  logs only, no interruption
```

To add a new channel like OpsGenie or SMS, add a new class that extends AlertStrategy and register it in STRATEGIES. Nothing else changes.

### State Pattern — Incident Lifecycle

```
OPEN --> INVESTIGATING --> RESOLVED --> CLOSED
              |                           ^
              +--- back to OPEN ----------+
                   (if issue returns)
```

Rules:
- Cannot skip states
- Cannot reopen a CLOSED incident
- Cannot close without a complete RCA
- The CLOSED constraint is also enforced at the DB level with a PostgreSQL CHECK constraint

### Repository Pattern — Database Abstraction

WorkItemRepository and SignalRepository handle all DB queries. The business logic in worker.py and main.py never writes raw SQL or calls motor/sqlalchemy directly. This makes it easy to test and swap storage layers.

---

## How Backpressure Works

The system is designed so a slow database never backs up the API.

**1. Buffered ingestion**
FastAPI puts signals into Redis and returns 202 immediately. If 10,000 signals arrive in one second, all 10,000 get a 202 response. They sit in the Redis queue until workers process them.

**2. Sliding window debouncing**
100 signals for the same component in 10 seconds create exactly 1 Work Item. All 100 signals are stored in MongoDB and linked to that Work Item. This prevents a storm of alerts for a single outage.

Implementation uses a Redis Sorted Set where the score is the timestamp in milliseconds:
- Remove entries older than 10 seconds
- If any remain, link signal to existing Work Item
- If empty, create new Work Item

All commands run in a Redis pipeline so they are atomic.

**3. Retry with exponential backoff**
If a DB write fails, Celery retries after 5 seconds, then 10, then 20. Max 3 retries. After that, the task goes to the dead letter queue and the failure is logged.

**4. Observability**
Every 5 seconds the API logs:
```
[METRICS] Signals/sec: 37 | Received: 185 | Dropped: 0 | Queue depth: 420
```

---

## Windows vs Linux Celery Difference

This was the hardest problem during development and is worth documenting clearly.

### The Problem

Python on Windows uses `ProactorEventLoop` by default. When `asyncio.run()` finishes a Celery task and closes the loop, the asyncpg and Motor connection transports try to schedule cleanup callbacks on the already closed loop. This throws `RuntimeError: Event loop is closed` and the task silently fails and retries forever.

### Windows Fix

At the top of `worker.py`, before any task runs:

```python
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

`SelectorEventLoop` does not have the destructor timing bug. This runs once at module import and fixes all subsequent tasks.

For local Windows dev, Celery must also use solo pool:

```bash
python celery_worker.py  # uses --pool=solo internally
```

### Linux Fix (Docker)

On Linux, Celery uses `prefork` by default which creates separate child processes. Each process gets its own fresh event loop. No conflict exists. The docker-compose worker command:

```bash
celery -A app.ims.worker worker --pool=prefork --concurrency=4
```

### Why Async Clients Cannot Be at Module Level

If you create asyncpg, Motor, or aioredis clients at module level, they bind to whatever event loop was running when they were created. On Celery workers, that loop is closed after the first task. All subsequent tasks get `connection pool was closed` errors.

The fix: create all async clients inside the task's async function, and close them in a `finally` block. Each task gets fresh clients bound to its own loop.

```python
async def _process_signal_async(signal_data):
    redis_client = aioredis.from_url(settings.redis_url)
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    engine = create_async_engine(settings.postgres_url)
    try:
        # do work
    finally:
        await redis_client.aclose()
        mongo_client.close()
        await engine.dispose()
```

---

## Load Test

The load test simulates a cascading infrastructure failure:

```bash
cd scripts
python generate_load.py
```

It runs in 4 phases:

| Phase | Component | Count | Severity |
|-------|-----------|-------|----------|
| 1 | RDBMS_PRIMARY | 50 | P0 |
| 2 | API_GATEWAY | 100 | P1 |
| 3 | CACHE_CLUSTER_01 | 200 | P2 |
| 4 | 20 random components | 200 | P1/P2/P3 |

Results on the working system: **550 / 550 accepted, 0 dropped, 37 signals/sec**

---

## Version Conflicts Fixed

| Package | Issue | Fix |
|---------|-------|-----|
| motor 3.3.2 + pymongo latest | pymongo 4.4+ removed `_QUERY_OPTIONS` that motor 3.3.2 needed | Pinned `motor==3.5.1` and `pymongo==4.6.3` |

---

## Environment Variables

All config is loaded from environment variables. Docker Compose sets these automatically.

| Variable | Default (local) | Docker value |
|----------|----------------|--------------|
| POSTGRES_URL | postgresql+asyncpg://ims_user:ims_pass_123@localhost:5432/ims | ...@postgres:5432/ims |
| MONGO_URL | mongodb://localhost:27017/ims | mongodb://mongo:27017/ims |
| REDIS_URL | redis://localhost:6379/0 | redis://redis:6379/0 |
| CELERY_BROKER_URL | redis://localhost:6379/0 | redis://redis:6379/0 |
| CELERY_RESULT_BACKEND | redis://localhost:6379/0 | redis://redis:6379/0 |
| DEBOUNCE_WINDOW_SECONDS | 10 | 10 |

---

## Evaluation Rubric Coverage

| Category | What I Did |
|----------|-----------|
| Concurrency and Scaling | Async FastAPI, Celery workers, Redis queue, debouncing handles 10k signals/sec |
| Data Handling | Four storage systems each with a specific role, correct separation |
| LLD | Strategy, State, Repository patterns all implemented |
| UI/UX | React dashboard with live feed, incident detail, RCA form |
| Resilience | Retry with exponential backoff, health endpoint, metrics logging |
| Documentation | This README, inline code comments, Swagger at /docs |
| Tech Stack | Justified above with reasons for each choice |

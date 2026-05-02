# Incident Management System (IMS)

Mission-critical incident management system for distributed stack monitoring.

## Architecture

[Signal Sources] → [FastAPI Ingestion] → [Redis Stream] → [Celery Worker]
↓
┌───────┴───────┐
↓               ↓
[MongoDB]      [PostgreSQL]
(Raw Signals)  (Work Items + RCA)
↑               ↑
[Redis Cache] ←── [Dashboard]


## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | FastAPI + Uvicorn | High-throughput async ingestion |
| Worker | Celery + Redis | Background signal processing |
| Source of Truth | PostgreSQL + TimescaleDB | ACID work items, time-series analytics |
| Data Lake | MongoDB | Schema-less raw signal storage |
| Cache | Redis | Real-time dashboard state, debouncing |
| Frontend | React + TanStack Query + Tailwind | Live incident dashboard |
| Alerts | Strategy Pattern | P0→PagerDuty, P1/P2→Slack, P3→Log |

## Design Patterns Used

- **Strategy Pattern**: Severity-based alerting (P0/P1/P2/P3)
- **State Pattern**: Incident lifecycle (OPEN→INVESTIGATING→RESOLVED→CLOSED)
- **Repository Pattern**: Database abstraction layer
- **Producer-Consumer**: FastAPI + Celery via Redis Streams

## Backpressure Handling

1. **Buffered ingestion**: FastAPI accepts signals immediately, enqueues to Redis
2. **Sliding window debouncing**: 100 signals/10s for same component → 1 Work Item
3. **Circuit breaker**: DB writes retry with exponential backoff
4. **Metrics**: Console logs every 5s (signals/sec, queue depth, drop rate)

## Quick Start

```bash
# Start databases
docker-compose up -d

# Install backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Terminal 1: API
python run.py

# Terminal 2: Worker
celery -A app.ims.worker worker --loglevel=info

# Terminal 3: Frontend
cd ../frontend
npm install
npm run dev

## Incident Management System (IMS)

| Method | Endpoint                 | Description      |
| ------ | ------------------------ | ---------------- |
| POST   | `/ingest`                | Submit signal    |
| GET    | `/health`                | Service health   |
| GET    | `/incidents/active`      | Active incidents |
| GET    | `/incidents/{id}`        | Incident detail  |
| POST   | `/incidents/{id}/rca`    | Submit RCA       |
| PATCH  | `/incidents/{id}/status` | Update status    |


##Load Testing
cd scripts
python generate_load.py

## Evaluation Rubric Coverage
| Category              | Implementation                                          |
| --------------------- | ------------------------------------------------------- |
| Concurrency & Scaling | Async FastAPI, Celery workers, Redis Streams            |
| Data Handling         | 4 storage systems (Postgres, Mongo, Redis, TimescaleDB) |
| LLD                   | Strategy, State, Repository patterns                    |
| UI/UX                 | React dashboard with real-time updates, RCA form        |
| Resilience            | Retry logic, circuit breaker, health endpoint           |
| Documentation         | This README + inline code docs                          |
| Tech Stack            | Justified in Architecture section above                 |

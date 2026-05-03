"""
generate_load.py — Fixed load generator.

BUGS FIXED:
1. session.post() was used as a raw coroutine inside gather — it's a context manager,
   so responses were _RequestContextManager objects, never ClientResponse.
   success count was always 0. Fixed by wrapping each call in a proper async helper.

2. datetime.utcnow().isoformat() produces naive datetime strings ("2026-05-03T12:00:00")
   which can cause Pydantic validation issues. Removed timestamp from payload — the
   server defaults it correctly via Optional[datetime] = None.
"""

import asyncio
import aiohttp
import json
import random
from datetime import datetime

COMPONENTS = [
    "API_GATEWAY", "MCP_HOST_01", "MCP_HOST_02",
    "CACHE_CLUSTER_01", "CACHE_CLUSTER_02",
    "RDBMS_PRIMARY", "RDBMS_REPLICA",
    "QUEUE_WORKERS", "SEARCH_INDEX"
]

BASE_URL = "http://localhost:8000"


async def send_signal(session: aiohttp.ClientSession, component: str, severity: str) -> bool:
    """
    Send a single signal. Returns True if accepted (202).

    Uses async with to properly handle the aiohttp context manager.
    """
    payload = {
        "component_id": component,
        "severity": severity,
        "payload": {
            "error_type": random.choice(["timeout", "connection_refused", "oom", "disk_full"]),
            "latency_ms": random.randint(100, 5000),
            "trace_id": f"trace-{random.randint(100000, 999999)}"
        }
        # timestamp omitted — server defaults to utcnow()
    }
    try:
        async with session.post(f"{BASE_URL}/ingest", json=payload) as resp:
            return resp.status == 202
    except Exception as e:
        print(f"  [ERROR] {component}: {e}")
        return False


async def burst_component(
    session: aiohttp.ClientSession,
    component: str,
    count: int,
    severity: str
) -> int:
    """Fire `count` signals for a component concurrently. Returns success count."""
    tasks = [send_signal(session, component, severity) for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if r is True)
    print(f"  [{severity}] {component}: {success}/{count} accepted")
    return success


async def simulate_cascading_failure():
    """
    Simulates a realistic cascading failure scenario:
    Phase 1: DB primary goes down (P0 burst)
    Phase 2: API gateway degrades (P1 burst)
    Phase 3: Cache cluster under pressure (P2 burst)
    Phase 4: Background noise across all components
    """
    connector = aiohttp.TCPConnector(limit=200)  # allow enough concurrent connections

    async with aiohttp.ClientSession(connector=connector) as session:
        # Verify API is reachable before hammering it
        try:
            async with session.get(f"{BASE_URL}/health") as resp:
                if resp.status != 200:
                    print(f"❌ API health check failed: {resp.status}")
                    return
                print("✅ API is healthy, starting load test\n")
        except Exception as e:
            print(f"❌ Cannot reach API at {BASE_URL}: {e}")
            return

        total_sent = 0
        total_accepted = 0

        print("=== PHASE 1: RDBMS PRIMARY FAILURE ===")
        n = await burst_component(session, "RDBMS_PRIMARY", 50, "P0")
        total_sent += 50
        total_accepted += n
        await asyncio.sleep(2)

        print("\n=== PHASE 2: API GATEWAY DEGRADATION ===")
        n = await burst_component(session, "API_GATEWAY", 100, "P1")
        total_sent += 100
        total_accepted += n
        await asyncio.sleep(3)

        print("\n=== PHASE 3: CACHE CLUSTER PRESSURE ===")
        n = await burst_component(session, "CACHE_CLUSTER_01", 200, "P2")
        total_sent += 200
        total_accepted += n

        print("\n=== PHASE 4: BACKGROUND NOISE (20 bursts × 10 signals) ===")
        tasks = [
            burst_component(
                session,
                random.choice(COMPONENTS),
                10,
                random.choice(["P1", "P2", "P3"])
            )
            for _ in range(20)
        ]
        results = await asyncio.gather(*tasks)
        total_sent += 20 * 10
        total_accepted += sum(results)

        print(f"\n=== LOAD TEST COMPLETE ===")
        print(f"Total signals sent:    {total_sent}")
        print(f"Total accepted (202):  {total_accepted}")
        print(f"Drop rate:             {(total_sent - total_accepted) / total_sent * 100:.1f}%")
        print(f"\nCheck active incidents: GET {BASE_URL}/incidents/active")


if __name__ == "__main__":
    asyncio.run(simulate_cascading_failure())
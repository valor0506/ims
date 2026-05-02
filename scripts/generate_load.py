import asyncio
import aiohttp
import json
import random
from datetime import datetime, timedelta

COMPONENTS = [
    "API_GATEWAY", "MCP_HOST_01", "MCP_HOST_02",
    "CACHE_CLUSTER_01", "CACHE_CLUSTER_02",
    "RDBMS_PRIMARY", "RDBMS_REPLICA",
    "QUEUE_WORKERS", "SEARCH_INDEX"
]

async def burst_component(session, component, count, severity):
    tasks = []
    for _ in range(count):
        payload = {
            "component_id": component,
            "severity": severity,
            "payload": {
                "error_type": random.choice(["timeout", "connection_refused", "oom", "disk_full"]),
                "latency_ms": random.randint(100, 5000),
                "trace_id": f"trace-{random.randint(100000, 999999)}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        tasks.append(session.post("http://localhost:8000/ingest", json=payload))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in responses if isinstance(r, aiohttp.ClientResponse) and r.status == 202)
    print(f"[BURST] {component}: {success}/{count} accepted")
    return success

async def simulate_cascading_failure():
    async with aiohttp.ClientSession() as session:
        print("=== PHASE 1: RDBMS PRIMARY FAILURE ===")
        await burst_component(session, "RDBMS_PRIMARY", 50, "P0")
        
        await asyncio.sleep(2)
        
        print("=== PHASE 2: API GATEWAY DEGRADATION ===")
        await burst_component(session, "API_GATEWAY", 100, "P1")
        
        await asyncio.sleep(3)
        
        print("=== PHASE 3: CACHE CLUSTER PRESSURE ===")
        await burst_component(session, "CACHE_CLUSTER_01", 200, "P2")
        
        print("=== PHASE 4: BACKGROUND NOISE ===")
        tasks = [
            burst_component(session, random.choice(COMPONENTS), 10, random.choice(["P1", "P2", "P3"]))
            for _ in range(20)
        ]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(simulate_cascading_failure())
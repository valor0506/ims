"""
debouncer.py — Fixed to accept an injected redis client.

ROOT CAUSE FIXED:
Previously imported the module-level redis_client singleton from redis_client.py.
That singleton is created at import time with no running event loop, and after
the first task's loop closes, it becomes permanently broken.

Now the redis client is injected at construction time from inside the task,
where a fresh loop is already running.
"""

import uuid
from datetime import datetime
from typing import Tuple


class SignalDebouncer:
    """
    Sliding window debouncer using Redis Sorted Sets.

    Problem: 100 signals for same Component ID in 10 seconds → 1 Work Item.
    Solution: Redis ZSET stores (work_item_id, timestamp). Check if any entry
    exists in the last N seconds before creating a new work item.
    """

    def __init__(self, window_seconds: int = 10, redis_client=None):
        """
        Args:
            window_seconds: Deduplication window size
            redis_client: An already-initialized async Redis client.
                          Must be created inside the running event loop.
                          Do NOT pass the module-level singleton.
        """
        if redis_client is None:
            raise ValueError(
                "redis_client must be injected. "
                "Do not use the module-level singleton from redis_client.py in Celery tasks."
            )
        self.redis = redis_client
        self.window_ms = window_seconds * 1000

    async def process(self, component_id: str, signal_data: bytes) -> Tuple[bool, str]:
        """
        Process signal for deduplication.

        Returns:
            (is_new_work_item, work_item_id)
            is_new_work_item = True if this is the first signal in the window
        """
        now = int(datetime.utcnow().timestamp() * 1000)  # milliseconds
        window_start = now - self.window_ms
        key = f"debounce:{component_id}"

        # Redis pipeline: batch multiple commands atomically
        pipe = self.redis.pipeline()

        # 1. Remove expired entries (sliding window cleanup)
        pipe.zremrangebyscore(key, 0, window_start)

        # 2. Check if window already has active entries
        pipe.zrange(key, 0, 0, withscores=False)

        # 3. Add current signal timestamp as temp placeholder
        temp_member = f"temp:{now}"
        pipe.zadd(key, {temp_member: now})

        # 4. Set TTL for auto-cleanup
        pipe.expire(key, self.window_ms // 1000 + 1)

        results = await pipe.execute()
        existing_members = results[1]  # zrange result

        if existing_members:
            # Window is active — deduplicate against existing work item
            work_item_id = existing_members[0]
            if isinstance(work_item_id, bytes):
                work_item_id = work_item_id.decode()

            # Remove the temp placeholder we added
            await self.redis.zrem(key, temp_member)

            # Skip temp entries — they indicate a race, not a real work item
            if work_item_id.startswith("temp:"):
                # Edge case: pipeline ran concurrently, generate new ID
                work_item_id = f"wi-{uuid.uuid4().hex[:12]}"
                await self.redis.zadd(key, {work_item_id: now})
                return True, work_item_id

            return False, work_item_id

        # No active window — this is a new incident
        work_item_id = f"wi-{uuid.uuid4().hex[:12]}"

        # Replace the temp member with the real work item ID
        await self.redis.zrem(key, temp_member)
        await self.redis.zadd(key, {work_item_id: now})

        return True, work_item_id
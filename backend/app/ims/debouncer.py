import uuid
from datetime import datetime
from typing import Tuple
from .redis_client import redis_client

class SignalDebouncer:
    """
    Sliding window debouncer using Redis Sorted Sets.
    
    Problem: 100 signals for same Component ID in 10 seconds should create 1 Work Item.
    Solution: Redis ZSET stores (work_item_id, timestamp). We check if any entry exists
    in the last 10 seconds before creating a new one.
    """
    
    def __init__(self, window_seconds: int = 10):
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
        
        # Redis pipeline: batch multiple commands for efficiency
        pipe = redis_client.pipeline()
        
        # 1. Remove expired entries (sliding window)
        pipe.zremrangebyscore(key, 0, window_start)
        
        # 2. Check if window already has active entries
        pipe.zrange(key, 0, 0, withscores=False)
        
        # 3. Add current signal timestamp
        temp_member = f"temp:{now}"
        pipe.zadd(key, {temp_member: now})
        
        # 4. Set TTL on key (auto-cleanup)
        pipe.expire(key, self.window_ms // 1000 + 1)
        
        # Execute all commands atomically
        results = await pipe.execute()
        existing_members = results[1]  # zrange result
        
        if existing_members:
            # Window exists - get the work_item_id (first member)
            work_item_id = existing_members[0]
            if isinstance(work_item_id, bytes):
                work_item_id = work_item_id.decode()
            
            # Remove the temp member we added (signal links to existing WI)
            await redis_client.zrem(key, temp_member)
            
            return False, work_item_id
        
        # New window - create work item ID
        work_item_id = f"wi-{uuid.uuid4().hex[:12]}"
        
        # Replace temp member with actual work_item_id
        await redis_client.zrem(key, temp_member)
        await redis_client.zadd(key, {work_item_id: now})
        
        return True, work_item_id
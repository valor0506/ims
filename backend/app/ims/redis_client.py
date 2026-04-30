import redis.asyncio as redis
from .config import settings

# Singleton Redis client
redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=False,  # We handle bytes manually for signals
)

async def init_redis():
    """Verify Redis connection on startup"""
    await redis_client.ping()
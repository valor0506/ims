from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

# Motor is the official async MongoDB driver for Python
mongo_client = AsyncIOMotorClient(settings.mongo_url)
db = mongo_client.get_database()  # Gets 'ims' from the URL

# Collections
raw_signals_collection = db.raw_signals

async def init_mongo_indexes():
    """Create indexes for performance"""
    await raw_signals_collection.create_index("work_item_id")
    await raw_signals_collection.create_index("component_id")
    await raw_signals_collection.create_index("ingested_at")
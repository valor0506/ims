from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base
from .config import settings

# Create async engine (connection pool to PostgreSQL)
engine = create_async_engine(
    settings.postgres_url,
    echo=False,  # Set True to see SQL queries in console
    pool_size=20,  # Keep 20 connections warm
    max_overflow=10,  # Allow 10 extra under load
    pool_pre_ping=True,  # Verify connection before using (prevents stale connections)
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit (better for async)
)

async def init_db():
    """Create all tables on startup"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Dependency for FastAPI - yields a database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """All configuration loaded from environment variables with defaults for local dev"""
    
    # PostgreSQL (Source of Truth)
    postgres_url: str = "postgresql+asyncpg://ims_user:ims_pass_123@localhost:5432/ims"
    
    # MongoDB (Data Lake - raw signals)
    mongo_url: str = "mongodb://localhost:27017/ims"
    
    # Redis (Cache + Queue + Debouncer)
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery (Task Queue)
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Rate Limiting
    rate_limit_per_second: int = 10000
    rate_limit_burst: int = 15000
    
    # Debouncing
    debounce_window_seconds: int = 10
    
    class Config:
        env_file = ".env"  # Will load from .env file if present

@lru_cache()
def get_settings() -> Settings:
    """Singleton pattern - load settings once, reuse everywhere"""
    return Settings()

settings = get_settings()
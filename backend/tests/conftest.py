import pytest
from app.core.database import engine
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

@pytest.fixture(autouse=True)
async def cleanup_after_test():
    yield
    await engine.dispose()

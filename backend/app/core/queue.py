from typing import Optional
import arq
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await arq.create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None

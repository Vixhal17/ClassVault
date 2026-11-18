import asyncio
import time
import uuid
from typing import AsyncGenerator, Optional
from fastapi import Request, HTTPException, status
import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool, _redis_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_pool is None or _redis_loop != current_loop or (_redis_loop and _redis_loop.is_closed()):
        _redis_pool = aioredis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
        _redis_loop = current_loop
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_redis_pool())


async def close_redis_pool():
    global _redis_pool, _redis_loop
    if _redis_pool:
        try:
            await _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None
        _redis_loop = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = await get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


def get_client_ip(request: Request) -> str:
    """Extract client IP, handling proxies safely."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


async def check_sliding_window_rate_limit(
    redis: aioredis.Redis,
    key_prefix: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> dict:
    """
    Sliding window rate limit implementation using Redis ZSET.
    Raises HTTPException(429) with standard rate limit headers when exceeded:
    - Retry-After
    - X-RateLimit-Limit
    - X-RateLimit-Remaining
    - X-RateLimit-Reset
    Returns rate limit metrics dict: {"limit": limit, "remaining": remaining, "reset": reset}
    """
    now = time.time()
    key = f"ratelimit:{key_prefix}:{identifier}"
    member = f"{now}:{uuid.uuid4().hex[:8]}"

    # Remove items older than window
    await redis.zremrangebyscore(key, 0, now - window_seconds)

    # Count items in window
    count = await redis.zcard(key)

    if count >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        if oldest:
            _, oldest_score = oldest[0]
            retry_after = int(oldest_score + window_seconds - now) + 1
        else:
            retry_after = window_seconds

        retry_after = max(1, retry_after)
        reset_time = int(now + retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
            },
        )

    # Add current request
    pipe = redis.pipeline()
    pipe.zadd(key, {member: now})
    pipe.expire(key, window_seconds + 5)
    await pipe.execute()

    remaining = max(0, limit - (count + 1))
    reset_time = int(now + window_seconds)
    return {
        "limit": limit,
        "remaining": remaining,
        "reset": reset_time,
    }

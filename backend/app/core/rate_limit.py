import time
import uuid
from typing import AsyncGenerator
from fastapi import Request, HTTPException, status
import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
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
):
    """
    Sliding window rate limit implementation using Redis ZSET.
    Raises HTTPException(429) with Retry-After header when exceeded.
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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Add current request
    pipe = redis.pipeline()
    pipe.zadd(key, {member: now})
    pipe.expire(key, window_seconds + 5)
    await pipe.execute()

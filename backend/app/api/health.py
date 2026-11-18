from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.core.database import engine
from app.services.storage import storage
from app.core.logging import logger

router = APIRouter(tags=["System"])
settings = get_settings()

@router.get("/health")
async def health_check():
    details = {
        "postgres": "unknown",
        "redis": "unknown",
        "qdrant": "unknown",
        "storage": "unknown"
    }
    healthy = True

    # Check PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        details["postgres"] = "healthy"
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        details["postgres"] = f"unhealthy: {str(e)}"
        healthy = False

    # Check Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pong = await r.ping()
        await r.aclose()
        if pong:
            details["redis"] = "healthy"
        else:
            details["redis"] = "unhealthy: no pong"
            healthy = False
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        details["redis"] = f"unhealthy: {str(e)}"
        healthy = False

    # Check Qdrant
    try:
        qdrant_client = AsyncQdrantClient(url=settings.QDRANT_URL, check_compatibility=False)
        await qdrant_client.get_collections()
        await qdrant_client.close()
        details["qdrant"] = "healthy"
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        details["qdrant"] = f"unhealthy: {str(e)}"
        healthy = False

    # Check Cloudflare R2 Storage
    if not storage.is_configured:
        details["storage"] = "placeholder (credentials pending)"
    else:
        storage_ok = await storage.ping()
        details["storage"] = "healthy" if storage_ok else "unhealthy"

    status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if healthy else "degraded",
            "services": details
        }
    )

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import logger
from app.core.rate_limit import get_client_ip, get_redis_client, check_sliding_window_rate_limit, close_redis_pool
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.enrollments import router as enrollments_router
from app.api.units import router as units_router
from app.api.admin import router as admin_router
from app.api.files import router as files_router
from app.api.chat import router as chat_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ClassVault API starting up...")
    logger.info(f"Frontend Origin allowed: {settings.FRONTEND_ORIGIN}")
    yield
    logger.info("ClassVault API shutting down...")
    await close_redis_pool()


app = FastAPI(
    title="ClassVault API",
    description="Secure course document management and RAG assistant",
    version="1.0.0",
    lifespan=lifespan,
)


# 1. Global Rate Limit Middleware
class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip CORS preflights, documentation, and health check endpoints
        if request.method == "OPTIONS" or request.url.path in (
            "/health",
            "/api/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ):
            return await call_next(request)

        ip = get_client_ip(request)
        try:
            redis = await get_redis_client()
            metrics = await check_sliding_window_rate_limit(
                redis=redis,
                key_prefix="global_ip",
                identifier=ip,
                limit=settings.GLOBAL_RATE_LIMIT_PER_MINUTE,
                window_seconds=60,
            )
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(metrics["limit"])
            response.headers["X-RateLimit-Remaining"] = str(metrics["remaining"])
            response.headers["X-RateLimit-Reset"] = str(metrics["reset"])
            return response
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        except Exception as e:
            logger.warning(f"Global rate limit check error: {e}")
            return await call_next(request)


app.add_middleware(GlobalRateLimitMiddleware)


# 2. Strict CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


# 3. Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(enrollments_router)
app.include_router(units_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(chat_router)

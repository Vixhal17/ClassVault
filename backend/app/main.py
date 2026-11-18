from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import logger
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.enrollments import router as enrollments_router
from app.api.units import router as units_router
from app.api.admin import router as admin_router
from app.api.files import router as files_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ClassVault API starting up...")
    logger.info(f"Frontend Origin allowed: {settings.FRONTEND_ORIGIN}")
    yield
    logger.info("ClassVault API shutting down...")

app = FastAPI(
    title="ClassVault API",
    description="Secure course document management and RAG assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Strict CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(enrollments_router)
app.include_router(units_router)
app.include_router(admin_router)
app.include_router(files_router)

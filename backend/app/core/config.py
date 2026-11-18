from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Database
    DATABASE_URL: str = "postgresql+asyncpg://classvault:classvault@localhost:5432/classvault"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Qdrant Vector DB
    QDRANT_URL: str = "http://localhost:6333"

    # Cloudflare R2 Storage (S3-compatible)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "classvault"

    # Auth & Security
    JWT_SECRET: str = "classvault_super_secret_jwt_key_change_in_production_min_32_chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False
    ALLOWED_EMAIL_DOMAIN: Optional[str] = None

    # Initial Admin Seeding
    ADMIN_EMAIL: str = "admin@classvault.edu"
    ADMIN_PASSWORD: str = "AdminPassword123!"

    # CORS & Web
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # LLM & RAG
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    RAG_HYBRID_ENABLED: bool = True
    CHAT_LIMIT_PER_HOUR: int = 20
    FILE_UPLOAD_LIMIT_PER_HOUR: int = 30
    GLOBAL_RATE_LIMIT_PER_MINUTE: int = 120


@lru_cache()
def get_settings() -> Settings:
    return Settings()

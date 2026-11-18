import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2 hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(user_id: str, role: str) -> str:
    """Create a short-lived access token (15 min)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": str(role),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, family_id: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Create a rotating refresh token (7 days).
    Returns (refresh_token_jwt, family_id, jti).
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    family = family_id or uuid.uuid4().hex
    jti = uuid.uuid4().hex

    payload = {
        "sub": str(user_id),
        "family_id": family,
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token, family, jti


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """Decode and validate a JWT."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        logger.warning(f"JWT decode error: {e}")
        return None


# Redis Refresh Token Family Rotation Management
async def save_refresh_token(redis: aioredis.Redis, user_id: str, family_id: str, jti: str):
    """Store active refresh token jti in Redis with 7-day TTL."""
    key = f"refresh:{user_id}:{family_id}"
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(key, jti, ex=ttl_seconds)


async def rotate_refresh_token(
    redis: aioredis.Redis, refresh_token: str
) -> Optional[Tuple[str, str, str]]:
    """
    Rotate a refresh token.
    Detects reuse: if an old jti is reused, revokes the whole token family.
    Returns (new_access_token, new_refresh_token, user_id) on success, or None.
    """
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None

    user_id = payload.get("sub")
    family_id = payload.get("family_id")
    presented_jti = payload.get("jti")

    if not user_id or not family_id or not presented_jti:
        return None

    key = f"refresh:{user_id}:{family_id}"
    active_jti = await redis.get(key)

    if not active_jti:
        # Token expired or family already revoked
        return None

    if active_jti != presented_jti:
        # REUSE DETECTED!
        # Revoke the entire family immediately to defend against token theft.
        logger.error(
            f"SECURITY: Refresh token reuse detected for user {user_id}, family {family_id}! Revoking family."
        )
        await redis.delete(key)
        return None

    # Valid rotation: generate new refresh token and access token
    new_refresh_token, _, new_jti = create_refresh_token(user_id=user_id, family_id=family_id)
    await save_refresh_token(redis, user_id, family_id, new_jti)

    return new_refresh_token, user_id, family_id


async def revoke_refresh_family(redis: aioredis.Redis, user_id: str, family_id: str):
    """Revoke a specific refresh token family on logout."""
    key = f"refresh:{user_id}:{family_id}"
    await redis.delete(key)

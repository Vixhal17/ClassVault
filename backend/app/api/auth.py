from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import get_redis, get_client_ip, check_sliding_window_rate_limit
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    save_refresh_token,
    rotate_refresh_token,
    revoke_refresh_family,
    decode_token,
)
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from app.services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()

COOKIE_NAME = "cv_refresh_token"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    ip = get_client_ip(request)

    # Rate limit: 5 registrations per hour per IP
    await check_sliding_window_rate_limit(
        redis=redis,
        key_prefix="register_ip",
        identifier=ip,
        limit=5,
        window_seconds=3600,
    )

    email = req.email.strip().lower()

    # Optional email domain restriction
    if settings.ALLOWED_EMAIL_DOMAIN:
        domain = f"@{settings.ALLOWED_EMAIL_DOMAIN.strip().lower()}"
        if not email.endswith(domain):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Registration is restricted to {settings.ALLOWED_EMAIL_DOMAIN} email addresses.",
            )

    # Check if user already exists
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # Self-signup creates STUDENTS ONLY
    user = User(
        name=req.name.strip(),
        email=email,
        password_hash=hash_password(req.password),
        role=UserRole.STUDENT,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await log_audit(
        db=db,
        user_id=user.id,
        action="register",
        target_type="user",
        target_id=str(user.id),
        ip=ip,
    )

    return user


@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    ip = get_client_ip(request)
    email = req.email.strip().lower()

    # Sliding-window rate limit on login: 5/min per IP and per email
    await check_sliding_window_rate_limit(
        redis=redis,
        key_prefix="login_ip",
        identifier=ip,
        limit=5,
        window_seconds=60,
    )
    await check_sliding_window_rate_limit(
        redis=redis,
        key_prefix="login_email",
        identifier=email,
        limit=5,
        window_seconds=60,
    )

    # Query user
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        await log_audit(
            db=db,
            user_id=user.id if user else None,
            action="login_failed",
            target_type="user",
            ip=ip,
            metadata={"email": email},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your account has been deactivated.",
        )

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    access_token = create_access_token(user_id=str(user.id), role=user.role.value)
    refresh_token, family_id, jti = create_refresh_token(user_id=str(user.id))

    # Save refresh token in Redis
    await save_refresh_token(redis, str(user.id), family_id, jti)

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    await log_audit(
        db=db,
        user_id=user.id,
        action="login_success",
        target_type="user",
        target_id=str(user.id),
        ip=ip,
    )

    return AuthResponse(
        access_token=access_token,
        user=user,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    refresh_token = request.cookies.get(COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing from request cookies.",
        )

    rotation_result = await rotate_refresh_token(redis, refresh_token)
    if not rotation_result:
        # Token invalid, expired, or reuse attack detected
        response.delete_cookie(key=COOKIE_NAME, path="/")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or reused refresh token. Please sign in again.",
        )

    new_refresh_token, user_id_str, _ = rotation_result

    # Fetch fresh user data from DB
    import uuid
    stmt = select(User).where(User.id == uuid.UUID(user_id_str))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        response.delete_cookie(key=COOKIE_NAME, path="/")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or no longer exists.",
        )

    # Create new access token
    new_access_token = create_access_token(user_id=str(user.id), role=user.role.value)

    # Set rotated refresh token cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=new_refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return AuthResponse(
        access_token=new_access_token,
        user=user,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    redis: aioredis.Redis = Depends(get_redis),
):
    refresh_token = request.cookies.get(COOKIE_NAME)
    if refresh_token:
        payload = decode_token(refresh_token)
        if payload and payload.get("sub") and payload.get("family_id"):
            await revoke_refresh_family(
                redis, payload.get("sub"), payload.get("family_id")
            )

    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import redis.asyncio as aioredis
from sqlalchemy import select

from app.main import app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole

settings = get_settings()


@pytest.fixture
async def clean_redis():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield


@pytest.mark.asyncio
async def test_student_registration(clean_redis):
    random_id = uuid.uuid4().hex[:6]
    email = f"student_{random_id}@test.edu"
    payload = {
        "name": "Test Student",
        "email": email,
        "password": "SecurePassword123!",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == email.lower()
        assert data["role"] == "student"  # Always student
        assert data["is_active"] is True

        # Duplicate email registration rejected
        res_dup = await ac.post("/auth/register", json=payload)
        assert res_dup.status_code == 400
        assert "already exists" in res_dup.json()["detail"]


@pytest.mark.asyncio
async def test_login_and_me_flow(clean_redis):
    random_id = uuid.uuid4().hex[:6]
    email = f"user_{random_id}@test.edu"
    password = "CorrectPassword123!"

    # Register
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/auth/register",
            json={"name": "Auth User", "email": email, "password": password},
        )

        # Login with invalid password
        res_invalid = await ac.post(
            "/auth/login",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert res_invalid.status_code == 401

        # Login with valid password
        res_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert res_login.status_code == 200
        login_data = res_login.json()
        access_token = login_data["access_token"]
        assert access_token is not None
        assert "cv_refresh_token" in res_login.cookies

        # Access /me with Bearer token
        res_me = await ac.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert res_me.status_code == 200
        assert res_me.json()["email"] == email


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_revocation(clean_redis):
    random_id = uuid.uuid4().hex[:6]
    email = f"rotate_{random_id}@test.edu"
    password = "RotatePassword123!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/auth/register",
            json={"name": "Rotate User", "email": email, "password": password},
        )

        res_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        old_refresh_cookie = res_login.cookies.get("cv_refresh_token")
        assert old_refresh_cookie is not None

        # 1. Normal rotation: use refresh token once
        ac.cookies.set("cv_refresh_token", old_refresh_cookie)
        res_refresh1 = await ac.post("/auth/refresh")
        assert res_refresh1.status_code == 200
        new_refresh_cookie = res_refresh1.cookies.get("cv_refresh_token")
        assert new_refresh_cookie != old_refresh_cookie
        new_access_token = res_refresh1.json()["access_token"]

        # 2. Token reuse detection: presenting the OLD refresh token again
        ac.cookies.set("cv_refresh_token", old_refresh_cookie)
        res_reuse = await ac.post("/auth/refresh")
        assert res_reuse.status_code == 401
        assert "Invalid, expired, or reused" in res_reuse.json()["detail"]

        # 3. Whole family revoked: the NEW token should now also be rejected
        ac.cookies.set("cv_refresh_token", new_refresh_cookie)
        res_family_dead = await ac.post("/auth/refresh")
        assert res_family_dead.status_code == 401


@pytest.mark.asyncio
async def test_logout(clean_redis):
    random_id = uuid.uuid4().hex[:6]
    email = f"logout_{random_id}@test.edu"
    password = "LogoutPassword123!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/auth/register",
            json={"name": "Logout User", "email": email, "password": password},
        )

        res_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        cookie = res_login.cookies.get("cv_refresh_token")

        # Logout
        ac.cookies.set("cv_refresh_token", cookie)
        res_logout = await ac.post("/auth/logout")
        assert res_logout.status_code == 200

        # Attempt to refresh after logout
        ac.cookies.set("cv_refresh_token", cookie)
        res_refresh = await ac.post("/auth/refresh")
        assert res_refresh.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_user_immediate_revocation(clean_redis):
    random_id = uuid.uuid4().hex[:6]
    email = f"deact_{random_id}@test.edu"
    password = "DeactPassword123!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_reg = await ac.post(
            "/auth/register",
            json={"name": "Deact User", "email": email, "password": password},
        )
        user_id = res_reg.json()["id"]

        res_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        access_token = res_login.json()["access_token"]

        # Deactivate user directly in DB
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == uuid.UUID(user_id))
            result = await session.execute(stmt)
            u = result.scalar_one()
            u.is_active = False
            await session.commit()

        # Immediate revocation check: access token should now be rejected
        res_me = await ac.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert res_me.status_code == 401
        assert "deactivated" in res_me.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_rate_limiting(clean_redis):
    email = f"ratelimit_{uuid.uuid4().hex[:6]}@test.edu"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First 5 login attempts
        for _ in range(5):
            res = await ac.post(
                "/auth/login",
                json={"email": email, "password": "WrongPassword!"},
            )
            assert res.status_code == 401

        # 6th attempt should hit rate limit (429)
        res_limit = await ac.post(
            "/auth/login",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert res_limit.status_code == 429
        assert "Retry-After" in res_limit.headers
        assert "Rate limit exceeded" in res_limit.json()["detail"]

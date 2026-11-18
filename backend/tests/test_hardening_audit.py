import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import redis.asyncio as aioredis
from sqlalchemy import select

from app.main import app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.core.rate_limit import check_sliding_window_rate_limit
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.unit import Unit
from app.models.file import File, FileStatus
from app.models.audit import AuditLog
from app.services.audit import log_audit

settings = get_settings()


@pytest.fixture
async def clean_redis():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield


async def create_user(name: str, role: UserRole) -> User:
    unique_email = f"{role.value}_{uuid.uuid4().hex[:6]}@classvault.edu"
    async with AsyncSessionLocal() as session:
        user = User(
            name=name,
            email=unique_email,
            password_hash=hash_password("Password123!"),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_security_headers():
    """Verify security headers are applied to HTTP responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        headers = res.headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("x-xss-protection") == "1; mode=block"
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "max-age=31536000" in headers.get("strict-transport-security", "")
        assert "default-src 'self'" in headers.get("content-security-policy", "")


@pytest.mark.asyncio
async def test_sliding_window_rate_limiting_headers(clean_redis):
    """Verify sliding window returns standard rate limit headers and 429 on limit."""
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    prefix = f"test_{uuid.uuid4().hex[:6]}"
    ident = "user_123"

    # Make 2 calls with limit=2
    m1 = await check_sliding_window_rate_limit(r, prefix, ident, limit=2, window_seconds=60)
    assert m1["limit"] == 2
    assert m1["remaining"] == 1

    m2 = await check_sliding_window_rate_limit(r, prefix, ident, limit=2, window_seconds=60)
    assert m2["limit"] == 2
    assert m2["remaining"] == 0

    # 3rd call must raise HTTPException(429) with Retry-After and rate limit headers
    with pytest.raises(Exception) as exc_info:
        await check_sliding_window_rate_limit(r, prefix, ident, limit=2, window_seconds=60)

    exc = exc_info.value
    assert exc.status_code == 429
    assert "Retry-After" in exc.headers
    assert exc.headers["X-RateLimit-Limit"] == "2"
    assert exc.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in exc.headers
    await r.aclose()


@pytest.mark.asyncio
async def test_global_ip_rate_limiting_middleware(clean_redis):
    """Verify GlobalRateLimitMiddleware attaches headers and rate limits."""
    transport = ASGITransport(app=app)
    client_ip = f"198.51.100.{uuid.uuid4().int % 250 + 1}"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check endpoint should bypass rate limiting
        res = await client.get("/health", headers={"x-forwarded-for": client_ip})
        assert res.status_code == 200

        # Non-health endpoint should receive rate limit headers
        res = await client.get("/courses", headers={"x-forwarded-for": client_ip})
        assert "x-ratelimit-limit" in res.headers
        assert "x-ratelimit-remaining" in res.headers
        assert "x-ratelimit-reset" in res.headers


@pytest.mark.asyncio
async def test_cache_invalidation_course_version(clean_redis):
    """Verify course_version counter bumps on file delete and restore."""
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    teacher = await create_user("Prof Cache", UserRole.TEACHER)
    token = create_access_token(teacher.id, teacher.role)

    async with AsyncSessionLocal() as session:
        course = Course(
            name="Cache Invalidation 101",
            code=f"CI_{uuid.uuid4().hex[:4]}",
            teacher_id=teacher.id,
            join_code=f"C{uuid.uuid4().hex[:5].upper()}",
        )
        session.add(course)
        await session.flush()
        unit = Unit(course_id=course.id, title="Unit 1", position=0)
        session.add(unit)
        await session.flush()
        file_rec = File(
            course_id=course.id,
            unit_id=unit.id,
            original_name="syllabus.pdf",
            storage_key=f"courses/{course.id}/units/{unit.id}/syllabus.pdf",
            size_bytes=1024,
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            page_count=2,
            status=FileStatus.READY,
        )
        session.add(file_rec)
        await session.commit()
        course_id = course.id
        file_id = file_rec.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Set initial course version to 5
        await r.set(f"course_version:{course_id}", 5)

        # 1. Soft-delete file -> course_version must increment to 6
        del_res = await client.delete(
            f"/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_res.status_code == 200
        v_after_del = await r.get(f"course_version:{course_id}")
        assert v_after_del == "6"

        # 2. Restore file -> course_version must increment to 7
        restore_res = await client.post(
            f"/files/{file_id}/restore",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert restore_res.status_code == 200
        v_after_restore = await r.get(f"course_version:{course_id}")
        assert v_after_restore == "7"

    await r.aclose()


@pytest.mark.asyncio
async def test_admin_audit_logs_api(clean_redis):
    """Verify GET /admin/audit-logs pagination, search, action filter, and RBAC."""
    admin = await create_user("Admin User", UserRole.ADMIN)
    teacher = await create_user("Teacher User", UserRole.TEACHER)
    student = await create_user("Student User", UserRole.STUDENT)

    admin_token = create_access_token(admin.id, admin.role)
    teacher_token = create_access_token(teacher.id, teacher.role)
    student_token = create_access_token(student.id, student.role)

    # Seed test audit log entries
    async with AsyncSessionLocal() as session:
        await log_audit(
            db=session,
            user_id=admin.id,
            action="admin_action_test",
            target_type="system",
            target_id="sys_1",
            metadata={"detail": "config update"},
        )
        await log_audit(
            db=session,
            user_id=teacher.id,
            action="FILE_UPLOAD",
            target_type="file",
            target_id="file_abc",
            metadata={"filename": "lecture1.pdf"},
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res_unauth = await client.get("/admin/audit-logs")
        assert res_unauth.status_code == 401

        # 2. Student -> 403 Forbidden
        res_student = await client.get(
            "/admin/audit-logs",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert res_student.status_code == 403

        # 3. Teacher -> 403 Forbidden
        res_teacher = await client.get(
            "/admin/audit-logs",
            headers={"Authorization": f"Bearer {teacher_token}"},
        )
        assert res_teacher.status_code == 403

        # 4. Admin -> 200 OK
        res_admin = await client.get(
            "/admin/audit-logs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin.status_code == 200
        data = res_admin.json()
        assert "total" in data
        assert "items" in data
        assert len(data["items"]) >= 2

        # 5. Filter by action
        res_filter = await client.get(
            "/admin/audit-logs?action=FILE_UPLOAD",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_filter.status_code == 200
        filtered_items = res_filter.json()["items"]
        assert all(item["action"] == "FILE_UPLOAD" for item in filtered_items)

        # 6. Filter by search
        res_search = await client.get(
            "/admin/audit-logs?search=admin_action_test",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_search.status_code == 200
        search_items = res_search.json()["items"]
        assert len(search_items) >= 1
        assert search_items[0]["action"] == "admin_action_test"

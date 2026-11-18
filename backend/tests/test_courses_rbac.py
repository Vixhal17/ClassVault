import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import redis.asyncio as aioredis
from sqlalchemy import select

from app.main import app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.unit import Unit

settings = get_settings()


@pytest.fixture
async def clean_redis():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield


async def create_test_user(name: str, role: UserRole) -> User:
    unique_email = f"{role.value}_{uuid.uuid4().hex[:6]}@univ.edu"
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
async def test_teacher_course_creation_and_isolation(clean_redis):
    teacher1 = await create_test_user("Prof A", UserRole.TEACHER)
    teacher2 = await create_test_user("Prof B", UserRole.TEACHER)
    student = await create_test_user("Student X", UserRole.STUDENT)

    t1_token = create_access_token(str(teacher1.id), teacher1.role.value)
    t2_token = create_access_token(str(teacher2.id), teacher2.role.value)
    s_token = create_access_token(str(student.id), student.role.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Teacher 1 creates course
        res = await ac.post(
            "/courses",
            headers={"Authorization": f"Bearer {t1_token}"},
            json={"name": "Operating Systems", "code": "CS401"},
        )
        assert res.status_code == 201
        course_data = res.json()
        course_id = course_data["id"]
        join_code = course_data["join_code"]
        assert join_code.startswith("CS401")

        # 2. Student cannot create a course (403)
        res_s_create = await ac.post(
            "/courses",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"name": "Hacked Course", "code": "HACK1"},
        )
        assert res_s_create.status_code == 403

        # 3. Teacher 2 cannot view or update Teacher 1's course (Anti-IDOR: 404)
        res_t2_get = await ac.get(
            f"/courses/{course_id}",
            headers={"Authorization": f"Bearer {t2_token}"},
        )
        assert res_t2_get.status_code == 404

        res_t2_patch = await ac.patch(
            f"/courses/{course_id}",
            headers={"Authorization": f"Bearer {t2_token}"},
            json={"name": "Hijacked Course"},
        )
        assert res_t2_patch.status_code == 404

        # 4. Teacher 2 cannot rotate Teacher 1's code (404)
        res_t2_rotate = await ac.post(
            f"/courses/{course_id}/rotate-code",
            headers={"Authorization": f"Bearer {t2_token}"},
        )
        assert res_t2_rotate.status_code == 404

        # 5. Teacher 1 can rotate own join code
        res_t1_rotate = await ac.post(
            f"/courses/{course_id}/rotate-code",
            headers={"Authorization": f"Bearer {t1_token}"},
        )
        assert res_t1_rotate.status_code == 200
        new_code = res_t1_rotate.json()["join_code"]
        assert new_code != join_code


@pytest.mark.asyncio
async def test_enrollment_lifecycle_and_immediate_revocation(clean_redis):
    teacher = await create_test_user("Prof C", UserRole.TEACHER)
    student = await create_test_user("Student Y", UserRole.STUDENT)

    t_token = create_access_token(str(teacher.id), teacher.role.value)
    s_token = create_access_token(str(student.id), student.role.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create course
        res_course = await ac.post(
            "/courses",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"name": "Computer Networks", "code": "CS402"},
        )
        course_id = res_course.json()["id"]
        join_code = res_course.json()["join_code"]

        # Student cannot view course before enrollment (Anti-IDOR: 404)
        res_unauth = await ac.get(
            f"/courses/{course_id}",
            headers={"Authorization": f"Bearer {s_token}"},
        )
        assert res_unauth.status_code == 404

        # 1. Student joins with code -> pending
        res_join = await ac.post(
            "/courses/join",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"code": join_code},
        )
        assert res_join.status_code == 201
        assert res_join.json()["status"] == "pending"
        enrollment_id = res_join.json()["id"]

        # Pending student still gets 404 on course details
        assert (await ac.get(f"/courses/{course_id}", headers={"Authorization": f"Bearer {s_token}"})).status_code == 404

        # 2. Teacher sees request in pending requests
        res_reqs = await ac.get(
            f"/courses/{course_id}/requests",
            headers={"Authorization": f"Bearer {t_token}"},
        )
        assert res_reqs.status_code == 200
        assert len(res_reqs.json()) == 1

        # 3. Teacher approves enrollment
        res_approve = await ac.patch(
            f"/enrollments/{enrollment_id}",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"status": "approved"},
        )
        assert res_approve.status_code == 200
        assert res_approve.json()["status"] == "approved"

        # 4. Now approved student can view course
        res_s_view = await ac.get(
            f"/courses/{course_id}",
            headers={"Authorization": f"Bearer {s_token}"},
        )
        assert res_s_view.status_code == 200
        assert res_s_view.json()["name"] == "Computer Networks"
        assert res_s_view.json()["join_code"] is None  # Join code is redacted for student!

        # 5. Teacher removes student -> status = removed
        res_remove = await ac.patch(
            f"/enrollments/{enrollment_id}",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"status": "removed"},
        )
        assert res_remove.status_code == 200

        # 6. Immediate revocation: student's next call returns 404 immediately
        res_revoked = await ac.get(
            f"/courses/{course_id}",
            headers={"Authorization": f"Bearer {s_token}"},
        )
        assert res_revoked.status_code == 404


@pytest.mark.asyncio
async def test_units_and_published_visibility(clean_redis):
    teacher = await create_test_user("Prof D", UserRole.TEACHER)
    student = await create_test_user("Student Z", UserRole.STUDENT)

    t_token = create_access_token(str(teacher.id), teacher.role.value)
    s_token = create_access_token(str(student.id), student.role.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_c = await ac.post(
            "/courses",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"name": "Algorithms", "code": "CS301"},
        )
        course_id = res_c.json()["id"]
        join_code = res_c.json()["join_code"]

        # Student joins and teacher approves
        res_j = await ac.post(
            "/courses/join",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"code": join_code},
        )
        e_id = res_j.json()["id"]
        await ac.patch(
            f"/enrollments/{e_id}",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"status": "approved"},
        )

        # Teacher creates Unit 1 (published)
        res_u1 = await ac.post(
            f"/courses/{course_id}/units",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"title": "Unit 1: Sorting", "position": 1},
        )
        assert res_u1.status_code == 201

        # Teacher creates Unit 2 (draft / unpublished)
        res_u2 = await ac.post(
            f"/courses/{course_id}/units",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"title": "Unit 2: Dynamic Programming", "position": 2},
        )
        u2_id = res_u2.json()["id"]
        await ac.patch(
            f"/units/{u2_id}",
            headers={"Authorization": f"Bearer {t_token}"},
            json={"is_published": False},
        )

        # Teacher sees both units (2)
        res_t_units = await ac.get(
            f"/courses/{course_id}/units",
            headers={"Authorization": f"Bearer {t_token}"},
        )
        assert len(res_t_units.json()) == 2

        # Enrolled student sees ONLY published unit (1)
        res_s_units = await ac.get(
            f"/courses/{course_id}/units",
            headers={"Authorization": f"Bearer {s_token}"},
        )
        assert len(res_s_units.json()) == 1
        assert res_s_units.json()[0]["title"] == "Unit 1: Sorting"


@pytest.mark.asyncio
async def test_join_code_rate_limit(clean_redis):
    student = await create_test_user("Rate Student", UserRole.STUDENT)
    s_token = create_access_token(str(student.id), student.role.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First 10 requests allowed
        for _ in range(10):
            res = await ac.post(
                "/courses/join",
                headers={"Authorization": f"Bearer {s_token}"},
                json={"code": "INVALID-CODE"},
            )
            assert res.status_code == 404

        # 11th request triggers rate limit (429)
        res_limited = await ac.post(
            "/courses/join",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"code": "INVALID-CODE"},
        )
        assert res_limited.status_code == 429
        assert "Retry-After" in res_limited.headers
        assert "Rate limit exceeded" in res_limited.json()["detail"]


@pytest.mark.asyncio
async def test_admin_teacher_creation(clean_redis):
    admin = await create_test_user("Super Admin", UserRole.ADMIN)
    student = await create_test_user("Normal Student", UserRole.STUDENT)

    a_token = create_access_token(str(admin.id), admin.role.value)
    s_token = create_access_token(str(student.id), student.role.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Student cannot create teacher (403)
        res_s = await ac.post(
            "/admin/teachers",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"name": "Prof Hacked", "email": "prof_hacked@univ.edu", "password": "Password123!"},
        )
        assert res_s.status_code == 403

        # Admin creates teacher
        teacher_email = f"prof_valid_{uuid.uuid4().hex[:6]}@univ.edu"
        res_a = await ac.post(
            "/admin/teachers",
            headers={"Authorization": f"Bearer {a_token}"},
            json={"name": "Prof Legitimate", "email": teacher_email, "password": "Password123!"},
        )
        assert res_a.status_code == 201
        assert res_a.json()["role"] == "teacher"

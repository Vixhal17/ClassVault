import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import pymupdf
from sqlalchemy import select
import redis.asyncio as aioredis

from app.main import app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.unit import Unit
from app.models.file import File, FileStatus
from app.worker.worker import process_pdf
from app.services.vector_store import get_vector_store

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


def create_dummy_pdf(text: str = "ClassVault Operating Systems Unit 1 Test Material") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_file_upload_validation(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Prof FileTester", UserRole.TEACHER)
        t_token = create_access_token(str(teacher.id), teacher.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}

        # Create course & unit
        c_res = await client.post("/courses", headers=t_headers, json={"name": "Networks", "code": "CS301"})
        assert c_res.status_code == 201
        course_id = c_res.json()["id"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Unit 1", "position": 1})
        assert u_res.status_code == 201
        unit_id = u_res.json()["id"]

        # 1. Non-PDF MIME type
        bad_mime = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("test.txt", b"plain text", "text/plain")},
        )
        assert bad_mime.status_code == 400
        assert "Invalid file type" in bad_mime.json()["detail"]

        # 2. Corrupted magic bytes (%PDF- missing)
        bad_magic = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("fake.pdf", b"NOT_A_PDF_CONTENT", "application/pdf")},
        )
        assert bad_magic.status_code == 400
        assert "lacks standard %PDF- header" in bad_magic.json()["detail"]

        # 3. Size limit exceeded (> 20 MB)
        large_pdf = b"%PDF-" + b"0" * (20 * 1024 * 1024 + 10)
        oversized = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("large.pdf", large_pdf, "application/pdf")},
        )
        assert oversized.status_code == 413

        # 4. Valid upload returns 202 Accepted
        valid_pdf = create_dummy_pdf()
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("unit1.pdf", valid_pdf, "application/pdf")},
        )
        assert upload_res.status_code == 202
        data = upload_res.json()
        assert "file_id" in data
        assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_student_visibility_rules(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Bob", UserRole.TEACHER)
        student = await create_test_user("Student Carol", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_token = create_access_token(str(student.id), student.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_headers = {"Authorization": f"Bearer {s_token}"}

        # Course, unit, enrollment
        c_res = await client.post("/courses", headers=t_headers, json={"name": "Algorithms", "code": "CS201"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Sorting", "position": 1})
        unit_id = u_res.json()["id"]

        # Student joins & teacher approves
        join_res = await client.post("/courses/join", headers=s_headers, json={"code": join_code})
        assert join_res.status_code == 201
        enrollment_id = join_res.json()["id"]
        await client.patch(f"/enrollments/{enrollment_id}", headers=t_headers, json={"status": "approved"})

        # Teacher uploads file
        pdf_bytes = create_dummy_pdf("Sorting algorithms: Quicksort and Mergesort analysis.")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("sorting.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]

        # 1. While status is 'queued', student receives 404 on direct status endpoint
        s_status = await client.get(f"/files/{file_id}", headers=s_headers)
        assert s_status.status_code == 404

        # 2. While status is 'queued', file is NOT listed in student's unit files
        s_unit_files = await client.get(f"/units/{unit_id}/files", headers=s_headers)
        assert s_unit_files.status_code == 200
        assert len(s_unit_files.json()) == 0

        # Teacher DOES see the queued file
        t_unit_files = await client.get(f"/units/{unit_id}/files", headers=t_headers)
        assert len(t_unit_files.json()) == 1
        assert t_unit_files.json()[0]["status"] == "queued"

        # 3. Simulate worker finishing ingestion (status = ready)
        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == uuid.UUID(file_id))
            f_rec = (await session.execute(stmt)).scalar_one()
            f_rec.status = FileStatus.READY
            f_rec.page_count = 1
            await session.commit()

        # Now student sees the ready file
        s_unit_files_ready = await client.get(f"/units/{unit_id}/files", headers=s_headers)
        assert len(s_unit_files_ready.json()) == 1
        assert s_unit_files_ready.json()[0]["status"] == "ready"

        s_status_ready = await client.get(f"/files/{file_id}", headers=s_headers)
        assert s_status_ready.status_code == 200
        assert s_status_ready.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_file_download_presigned_url(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Dave", UserRole.TEACHER)
        student_approved = await create_test_user("Student Approved", UserRole.STUDENT)
        student_other = await create_test_user("Student Other", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_app_token = create_access_token(str(student_approved.id), student_approved.role.value)
        s_other_token = create_access_token(str(student_other.id), student_other.role.value)

        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_app_headers = {"Authorization": f"Bearer {s_app_token}"}
        s_other_headers = {"Authorization": f"Bearer {s_other_token}"}

        c_res = await client.post("/courses", headers=t_headers, json={"name": "Databases", "code": "CS402"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Indexing", "position": 1})
        unit_id = u_res.json()["id"]

        pdf_bytes = create_dummy_pdf("B-Trees and Hash Indexes")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("indexing.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]

        # Mark ready
        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == uuid.UUID(file_id))
            f_rec = (await session.execute(stmt)).scalar_one()
            f_rec.status = FileStatus.READY
            await session.commit()

        # Teacher can download
        t_down = await client.get(f"/files/{file_id}/download", headers=t_headers)
        assert t_down.status_code == 200
        assert "download_url" in t_down.json()
        assert t_down.json()["expires_in"] == 60

        # Unenrolled student cannot download (404 anti-IDOR)
        s_other_down = await client.get(f"/files/{file_id}/download", headers=s_other_headers)
        assert s_other_down.status_code == 404

        # Approved student CAN download
        join_res = await client.post("/courses/join", headers=s_app_headers, json={"code": join_code})
        assert join_res.status_code == 201
        enrollment_id = join_res.json()["id"]
        await client.patch(f"/enrollments/{enrollment_id}", headers=t_headers, json={"status": "approved"})

        s_down_approved = await client.get(f"/files/{file_id}/download", headers=s_app_headers)
        assert s_down_approved.status_code == 200
        assert "download_url" in s_down_approved.json()


@pytest.mark.asyncio
async def test_soft_delete_and_restore(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Eve", UserRole.TEACHER)
        t_token = create_access_token(str(teacher.id), teacher.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}

        c_res = await client.post("/courses", headers=t_headers, json={"name": "Compilers", "code": "CS501"})
        course_id = c_res.json()["id"]
        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Lexing", "position": 1})
        unit_id = u_res.json()["id"]

        pdf_bytes = create_dummy_pdf("Lexical analysis and DFAs")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("lexing.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]

        # Soft delete file
        del_res = await client.delete(f"/files/{file_id}", headers=t_headers)
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # Teacher lists files: not visible by default
        active_files = await client.get(f"/units/{unit_id}/files", headers=t_headers)
        assert len(active_files.json()) == 0

        # Teacher lists with include_deleted=true (Recycle bin)
        recycle_files = await client.get(f"/units/{unit_id}/files?include_deleted=true", headers=t_headers)
        assert len(recycle_files.json()) == 1
        assert recycle_files.json()[0]["deleted_at"] is not None

        # Restore file
        restore_res = await client.post(f"/files/{file_id}/restore", headers=t_headers)
        assert restore_res.status_code == 200
        assert restore_res.json()["status"] == "queued"
        assert restore_res.json()["deleted_at"] is None

        # Verify visible again
        restored_list = await client.get(f"/units/{unit_id}/files", headers=t_headers)
        assert len(restored_list.json()) == 1


@pytest.mark.asyncio
async def test_arq_process_pdf_execution(clean_redis):
    # Test worker process_pdf task directly
    teacher = await create_test_user("Worker Test Teacher", UserRole.TEACHER)
    t_token = create_access_token(str(teacher.id), teacher.role.value)
    t_headers = {"Authorization": f"Bearer {t_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c_res = await client.post("/courses", headers=t_headers, json={"name": "Architecture", "code": "CS102"})
        course_id = c_res.json()["id"]
        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Pipelines", "position": 1})
        unit_id = u_res.json()["id"]

        pdf_bytes = create_dummy_pdf("Pipelining hazard detection: Structural, Data, and Control hazards.")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("pipelining.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]

    # Execute worker task
    ctx = {"job_try": 1, "redis": None}
    worker_result = await process_pdf(ctx, file_id)
    assert worker_result["status"] == "ready"
    assert worker_result["pages"] == 1
    assert worker_result["chunks"] >= 1

    # Check DB status is ready
    async with AsyncSessionLocal() as session:
        stmt = select(File).where(File.id == uuid.UUID(file_id))
        f_rec = (await session.execute(stmt)).scalar_one()
        assert f_rec.status == FileStatus.READY
        assert f_rec.page_count == 1
        assert f_rec.error_msg is None

    # Check vectors exist in Qdrant
    vstore = get_vector_store()
    search_results = await vstore.search(course_id=course_id, query="pipelining hazards", top_k=5)
    assert len(search_results) >= 1
    assert "hazard" in search_results[0].text.lower()

import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import pymupdf
import redis.asyncio as aioredis
from sqlalchemy import select

from app.main import app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole
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


def create_course_pdf(title: str, text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"{title}\n\n{text}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_rag_chat_and_citations(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher CS", UserRole.TEACHER)
        student = await create_test_user("Student Learner", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_token = create_access_token(str(student.id), student.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_headers = {"Authorization": f"Bearer {s_token}"}

        # Course & unit
        c_res = await client.post("/courses", headers=t_headers, json={"name": "Operating Systems", "code": "CS401"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Virtual Memory", "position": 1})
        unit_id = u_res.json()["id"]

        # Student joins & teacher approves
        join_res = await client.post("/courses/join", headers=s_headers, json={"code": join_code})
        enrollment_id = join_res.json()["id"]
        await client.patch(f"/enrollments/{enrollment_id}", headers=t_headers, json={"status": "approved"})

        # Teacher uploads course PDF
        pdf_bytes = create_course_pdf(
            "Page Tables and TLB",
            "A Translation Lookaside Buffer (TLB) is a hardware cache that stores recent virtual-to-physical address translations."
        )
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("virtual-memory.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]

        # Ingest document
        ctx = {"job_try": 1, "redis": None}
        worker_res = await process_pdf(ctx, file_id)
        assert worker_res["status"] == "ready"

        # 1. Ask question directly from the document
        chat_res = await client.post(
            f"/courses/{course_id}/chat",
            headers=s_headers,
            json={"question": "What is a Translation Lookaside Buffer TLB?"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert "tlb" in data["answer"].lower() or "translation" in data["answer"].lower()
        assert len(data["sources"]) >= 1
        assert data["sources"][0]["file_name"] == "virtual-memory.pdf"
        assert data["sources"][0]["page"] == 1
        message_id = data["id"]

        # 2. Student rates answer as helpful
        fb_res = await client.post(
            f"/chat/{message_id}/feedback",
            headers=s_headers,
            json={"rating": "helpful"},
        )
        assert fb_res.status_code == 200
        assert fb_res.json()["rating"] == "helpful"

        # 3. Check chat history
        hist_res = await client.get(f"/courses/{course_id}/chat", headers=s_headers)
        assert hist_res.status_code == 200
        assert len(hist_res.json()) == 1
        assert hist_res.json()[0]["rating"] == "helpful"


@pytest.mark.asyncio
async def test_rag_streaming_sse(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Stream", UserRole.TEACHER)
        student = await create_test_user("Student Stream", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_token = create_access_token(str(student.id), student.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_headers = {"Authorization": f"Bearer {s_token}"}

        c_res = await client.post("/courses", headers=t_headers, json={"name": "Compilers", "code": "CS403"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "Syntax Analysis", "position": 1})
        unit_id = u_res.json()["id"]

        join_res = await client.post("/courses/join", headers=s_headers, json={"code": join_code})
        await client.patch(f"/enrollments/{join_res.json()['id']}", headers=t_headers, json={"status": "approved"})

        pdf_bytes = create_course_pdf("LR Parsing", "LR parsers are bottom-up shift-reduce parsers for context-free grammars.")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("parsers.pdf", pdf_bytes, "application/pdf")},
        )
        await process_pdf({"job_try": 1, "redis": None}, upload_res.json()["file_id"])

        # Call streaming endpoint
        stream_res = await client.post(
            f"/courses/{course_id}/chat/stream",
            headers=s_headers,
            json={"question": "What is an LR parser?"},
        )
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers["content-type"]

        body = stream_res.text
        assert "event: sources" in body
        assert "parsers.pdf" in body
        assert "event: token" in body
        assert "event: done" in body


@pytest.mark.asyncio
async def test_redis_cache_invalidation(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Cache", UserRole.TEACHER)
        student = await create_test_user("Student Cache", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_token = create_access_token(str(student.id), student.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_headers = {"Authorization": f"Bearer {s_token}"}

        c_res = await client.post("/courses", headers=t_headers, json={"name": "Networks", "code": "CS302"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        u_res = await client.post(f"/courses/{course_id}/units", headers=t_headers, json={"title": "TCP", "position": 1})
        unit_id = u_res.json()["id"]

        join_res = await client.post("/courses/join", headers=s_headers, json={"code": join_code})
        await client.patch(f"/enrollments/{join_res.json()['id']}", headers=t_headers, json={"status": "approved"})

        pdf_bytes = create_course_pdf("TCP Handshake", "TCP uses a three-way handshake: SYN, SYN-ACK, ACK.")
        upload_res = await client.post(
            f"/units/{unit_id}/files",
            headers=t_headers,
            files={"file": ("tcp.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = upload_res.json()["file_id"]
        await process_pdf({"job_try": 1, "redis": None}, file_id)

        # First request populates cache
        r1 = await client.post(f"/courses/{course_id}/chat", headers=s_headers, json={"question": "What is the TCP handshake?"})
        assert r1.status_code == 200

        # Second identical question hits cache instantly
        r2 = await client.post(f"/courses/{course_id}/chat", headers=s_headers, json={"question": "What is the TCP handshake?"})
        assert r2.status_code == 200
        assert r2.json()["answer"] == r1.json()["answer"]

        # Deleting the file increments course_version in Redis, invalidating old cache
        del_res = await client.delete(f"/files/{file_id}", headers=t_headers)
        assert del_res.status_code == 200

        # Third request after deletion receives unanswerable response
        r3 = await client.post(f"/courses/{course_id}/chat", headers=s_headers, json={"question": "What is the TCP handshake?"})
        assert r3.status_code == 200
        assert "couldn't find" in r3.json()["answer"].lower()


@pytest.mark.asyncio
async def test_chat_rate_limiting(clean_redis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        teacher = await create_test_user("Teacher Limit", UserRole.TEACHER)
        student = await create_test_user("Student Limit", UserRole.STUDENT)

        t_token = create_access_token(str(teacher.id), teacher.role.value)
        s_token = create_access_token(str(student.id), student.role.value)
        t_headers = {"Authorization": f"Bearer {t_token}"}
        s_headers = {"Authorization": f"Bearer {s_token}"}

        c_res = await client.post("/courses", headers=t_headers, json={"name": "Security", "code": "CS601"})
        course_id = c_res.json()["id"]
        join_code = c_res.json()["join_code"]

        join_res = await client.post("/courses/join", headers=s_headers, json={"code": join_code})
        await client.patch(f"/enrollments/{join_res.json()['id']}", headers=t_headers, json={"status": "approved"})

        # Submit 20 questions (allowed)
        for i in range(20):
            res = await client.post(f"/courses/{course_id}/chat", headers=s_headers, json={"question": f"Question {i}?"})
            assert res.status_code == 200

        # 21st request exceeds hourly limit of 20
        res_blocked = await client.post(f"/courses/{course_id}/chat", headers=s_headers, json={"question": "Question 21?"})
        assert res_blocked.status_code == 429
        assert "Rate limit exceeded" in res_blocked.json()["detail"]

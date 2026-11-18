import asyncio
import os
import shutil
import uuid
from playwright.async_api import async_playwright
import httpx
import pymupdf

API_URL = "http://localhost:8000"
WEB_URL = "http://localhost:3000"


def make_pdf(title: str, body: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"{title}\n\n{body}")
    b = doc.tobytes()
    doc.close()
    return b


async def setup_and_capture():
    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)
    artifact_dir = r"C:\Users\Vishal\.gemini\antigravity\brain\01d20605-c8dd-48d7-a828-90d34f645bd3"

    client = httpx.AsyncClient(base_url=API_URL, timeout=15.0)

    # 1. Login as admin
    admin_login = await client.post(
        "/auth/login",
        json={"email": "admin@classvault.edu", "password": "AdminPassword123!"},
    )
    admin_token = admin_login.json()["access_token"]

    # 2. Create teacher & student
    teacher_email = f"prof_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post(
        "/admin/teachers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Prof. Leslie Lamport", "email": teacher_email, "password": "TeacherPassword123!"},
    )

    student_email = f"student_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post(
        "/auth/register",
        json={"name": "Alex Mercer", "email": student_email, "password": "StudentPassword123!"},
    )
    s_login = await client.post(
        "/auth/login",
        json={"email": student_email, "password": "StudentPassword123!"},
    )
    student_token = s_login.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 3. Login as teacher
    t_login = await client.post("/auth/login", json={"email": teacher_email, "password": "TeacherPassword123!"})
    t_token = t_login.json()["access_token"]
    t_headers = {"Authorization": f"Bearer {t_token}"}

    # 4. Teacher creates course & unit
    c_res = await client.post(
        "/courses",
        headers=t_headers,
        json={"name": "Distributed Systems", "code": "CS602"},
    )
    course = c_res.json()
    course_id = course["id"]
    join_code = course["join_code"]

    u_res = await client.post(
        f"/courses/{course_id}/units",
        headers=t_headers,
        json={"title": "Unit 1: Consensus & Paxos", "position": 1},
    )
    unit_id = u_res.json()["id"]

    # Student joins & teacher approves
    join_res = await client.post("/courses/join", headers=student_headers, json={"code": join_code})
    enrollment_id = join_res.json()["id"]
    await client.patch(f"/enrollments/{enrollment_id}", headers=t_headers, json={"status": "approved"})

    # 5. Teacher uploads and ingests PDF
    pdf_bytes = make_pdf(
        "Paxos Consensus Protocol",
        "Paxos achieves consensus in asynchronous networks. The protocol operates in two phases: Prepare-Promise and Propose-Accept."
    )
    f_res = await client.post(
        f"/units/{unit_id}/files",
        headers=t_headers,
        files={"file": ("paxos-consensus-notes.pdf", pdf_bytes, "application/pdf")},
    )
    file_id = f_res.json()["file_id"]

    from app.worker.worker import process_pdf
    await process_pdf({"job_try": 1, "redis": None}, file_id)

    # 6. Ask question to populate chat history
    await client.post(
        f"/courses/{course_id}/chat",
        headers=student_headers,
        json={"question": "What are the two phases of the Paxos protocol?"},
    )

    # 7. Capture screenshots with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Desktop 1280px
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        await page.goto(f"{WEB_URL}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        await page.fill('input[type="email"]', student_email)
        await page.fill('input[type="password"]', "StudentPassword123!")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/courses")
        await page.wait_for_timeout(1000)

        await page.goto(f"{WEB_URL}/courses/{course_id}?tab=ask", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        p_chat_desktop = os.path.join(out_dir, "chat-desktop-1280px.png")
        await page.screenshot(path=p_chat_desktop, full_page=True)
        print(f"Captured: {p_chat_desktop}")

        await context.close()

        # Mobile 390px
        m_context = await browser.new_context(viewport={"width": 390, "height": 844})
        m_page = await m_context.new_page()

        await m_page.goto(f"{WEB_URL}/login", wait_until="domcontentloaded")
        await m_page.wait_for_timeout(1000)
        await m_page.fill('input[type="email"]', student_email)
        await m_page.fill('input[type="password"]', "StudentPassword123!")
        await m_page.click('button[type="submit"]')
        await m_page.wait_for_url("**/courses")
        await m_page.wait_for_timeout(1000)

        await m_page.goto(f"{WEB_URL}/courses/{course_id}?tab=ask", wait_until="networkidle")
        await m_page.wait_for_timeout(2000)

        p_chat_mobile = os.path.join(out_dir, "chat-mobile-390px.png")
        await m_page.screenshot(path=p_chat_mobile, full_page=True)
        print(f"Captured: {p_chat_mobile}")

        await m_context.close()
        await browser.close()

    for f in ["chat-desktop-1280px.png", "chat-mobile-390px.png"]:
        src = os.path.join(out_dir, f)
        if os.path.exists(src):
            dst = os.path.join(artifact_dir, f)
            shutil.copy2(src, dst)
            print(f"Copied to artifact dir: {dst}")

    print("Phase 4 visual capture completed.")


if __name__ == "__main__":
    asyncio.run(setup_and_capture())

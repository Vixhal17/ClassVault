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

    # 2. Create teacher
    teacher_email = f"prof_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post(
        "/admin/teachers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Prof. Donald Knuth", "email": teacher_email, "password": "TeacherPassword123!"},
    )

    # 3. Login as teacher
    t_login = await client.post("/auth/login", json={"email": teacher_email, "password": "TeacherPassword123!"})
    t_token = t_login.json()["access_token"]
    t_headers = {"Authorization": f"Bearer {t_token}"}

    # 4. Teacher creates course & unit
    c_res = await client.post(
        "/courses",
        headers=t_headers,
        json={"name": "Analysis of Algorithms", "code": "CS502"},
    )
    course = c_res.json()
    course_id = course["id"]

    u_res = await client.post(
        f"/courses/{course_id}/units",
        headers=t_headers,
        json={"title": "Unit 1: Asymptotic Complexity & Divide-and-Conquer", "position": 1},
    )
    unit_id = u_res.json()["id"]

    u2_res = await client.post(
        f"/courses/{course_id}/units",
        headers=t_headers,
        json={"title": "Unit 2: Dynamic Programming & Greedy Algorithms", "position": 2},
    )
    unit2_id = u2_res.json()["id"]

    # 5. Upload files to Unit 1
    # File 1: Master Theorem (ready)
    pdf1 = make_pdf("Master Theorem", "T(n) = aT(n/b) + f(n). Solving divide-and-conquer recurrences.")
    f1_res = await client.post(
        f"/units/{unit_id}/files",
        headers=t_headers,
        files={"file": ("master-theorem-notes.pdf", pdf1, "application/pdf")},
    )
    file1_id = f1_res.json()["file_id"]

    # Ingest File 1 using worker task
    from app.worker.worker import process_pdf
    await process_pdf({"job_try": 1, "redis": None}, file1_id)

    # File 2: Strassen Algorithm (queued / processing)
    pdf2 = make_pdf("Strassen Algorithm", "Matrix multiplication in sub-cubic time O(n^2.807).")
    f2_res = await client.post(
        f"/units/{unit_id}/files",
        headers=t_headers,
        files={"file": ("strassen-matrix-multiplication.pdf", pdf2, "application/pdf")},
    )

    # File 3: Upload and soft-delete for Recycle Bin
    pdf3 = make_pdf("Deleted Draft Notes", "Preliminary draft notes to be recycled.")
    f3_res = await client.post(
        f"/units/{unit_id}/files",
        headers=t_headers,
        files={"file": ("draft-lecture-notes-old.pdf", pdf3, "application/pdf")},
    )
    file3_id = f3_res.json()["file_id"]
    await client.delete(f"/files/{file3_id}", headers=t_headers)

    # 6. Capture with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Desktop 1280px
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # Login in UI
        await page.goto(f"{WEB_URL}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        await page.fill('input[type="email"]', teacher_email)
        await page.fill('input[type="password"]', "TeacherPassword123!")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        # Navigate to course detail
        await page.goto(f"{WEB_URL}/courses/{course_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        p_materials_desktop = os.path.join(out_dir, "materials-desktop-1280px.png")
        await page.screenshot(path=p_materials_desktop, full_page=True)
        print(f"Captured: {p_materials_desktop}")

        # Click "Recycle Bin" button to show deleted files
        try:
            await page.click('button:has-text("Recycle Bin")')
            await page.wait_for_timeout(1000)
            p_recycle_desktop = os.path.join(out_dir, "recycle-bin-desktop-1280px.png")
            await page.screenshot(path=p_recycle_desktop, full_page=True)
            print(f"Captured: {p_recycle_desktop}")
        except Exception as e:
            print(f"Recycle bin click: {e}")

        await context.close()

        # Mobile 390px
        m_context = await browser.new_context(viewport={"width": 390, "height": 844})
        m_page = await m_context.new_page()

        await m_page.goto(f"{WEB_URL}/login", wait_until="domcontentloaded")
        await m_page.wait_for_timeout(1000)
        await m_page.fill('input[type="email"]', teacher_email)
        await m_page.fill('input[type="password"]', "TeacherPassword123!")
        await m_page.click('button[type="submit"]')
        await m_page.wait_for_timeout(2000)

        await m_page.goto(f"{WEB_URL}/courses/{course_id}", wait_until="domcontentloaded")
        await m_page.wait_for_timeout(2000)

        p_materials_mobile = os.path.join(out_dir, "materials-mobile-390px.png")
        await m_page.screenshot(path=p_materials_mobile, full_page=True)
        print(f"Captured: {p_materials_mobile}")

        await m_context.close()
        await browser.close()

    # Copy to artifact dir
    for f in ["materials-desktop-1280px.png", "recycle-bin-desktop-1280px.png", "materials-mobile-390px.png"]:
        src = os.path.join(out_dir, f)
        if os.path.exists(src):
            dst = os.path.join(artifact_dir, f)
            shutil.copy2(src, dst)
            print(f"Copied to artifact dir: {dst}")

    print("Phase 3 visual verification completed.")


if __name__ == "__main__":
    asyncio.run(setup_and_capture())

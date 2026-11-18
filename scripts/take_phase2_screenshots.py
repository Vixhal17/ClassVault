import asyncio
import os
import shutil
import uuid
from playwright.async_api import async_playwright
import httpx

API_URL = "http://localhost:8000"
WEB_URL = "http://localhost:3000"

async def setup_and_capture():
    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)
    artifact_dir = r"C:\Users\Vishal\.gemini\antigravity\brain\01d20605-c8dd-48d7-a828-90d34f645bd3"

    # 1. Create teacher and student directly via API
    client = httpx.AsyncClient(base_url=API_URL, timeout=10.0)

    # Login as admin to create teacher
    admin_login = await client.post("/auth/login", json={"email": "admin@classvault.edu", "password": "AdminPassword123!"})
    admin_token = admin_login.json()["access_token"]

    teacher_email = f"prof_{uuid.uuid4().hex[:4]}@univ.edu"
    teacher_res = await client.post(
        "/admin/teachers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Prof. Alan Turing", "email": teacher_email, "password": "TeacherPassword123!"},
    )
    assert teacher_res.status_code == 201

    # Login as teacher
    t_login = await client.post("/auth/login", json={"email": teacher_email, "password": "TeacherPassword123!"})
    t_token = t_login.json()["access_token"]

    # Teacher creates course
    c_res = await client.post(
        "/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Operating Systems", "code": "CS401"},
    )
    course = c_res.json()
    course_id = course["id"]
    join_code = course["join_code"]

    # Create units
    await client.post(
        f"/courses/{course_id}/units",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"title": "Unit 1: Memory Virtualization", "position": 1},
    )
    await client.post(
        f"/courses/{course_id}/units",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"title": "Unit 2: Process Scheduling", "position": 2},
    )

    # Register student 1 and join
    s1_email = f"student1_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post("/auth/register", json={"name": "Aarav Sharma", "email": s1_email, "password": "StudentPassword123!"})
    s1_login = await client.post("/auth/login", json={"email": s1_email, "password": "StudentPassword123!"})
    s1_token = s1_login.json()["access_token"]
    s1_join = await client.post("/courses/join", headers={"Authorization": f"Bearer {s1_token}"}, json={"code": join_code})
    s1_enroll_id = s1_join.json()["id"]

    # Approve student 1
    await client.patch(f"/enrollments/{s1_enroll_id}", headers={"Authorization": f"Bearer {t_token}"}, json={"status": "approved"})

    # Register student 2 and join (remains pending)
    s2_email = f"student2_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post("/auth/register", json={"name": "Diya Patel", "email": s2_email, "password": "StudentPassword123!"})
    s2_login = await client.post("/auth/login", json={"email": s2_email, "password": "StudentPassword123!"})
    s2_token = s2_login.json()["access_token"]
    await client.post("/courses/join", headers={"Authorization": f"Bearer {s2_token}"}, json={"code": join_code})

    await client.aclose()

    # 2. Capture screenshots with Playwright logged in as teacher
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()

        # Login in browser
        page = await context.new_page()
        await page.goto(f"{WEB_URL}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        await page.fill('input[type="email"]', teacher_email)
        await page.fill('input[type="password"]', "TeacherPassword123!")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(1000)

        # Desktop 1280px - Courses List
        await page.set_viewport_size({"width": 1280, "height": 900})
        await page.goto(f"{WEB_URL}/courses", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        desk_courses_path = os.path.join(out_dir, "courses-desktop-1280px.png")
        await page.screenshot(path=desk_courses_path, full_page=True)
        print(f"Captured: {desk_courses_path}")

        # Mobile 390px - Courses List
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(f"{WEB_URL}/courses", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        mob_courses_path = os.path.join(out_dir, "courses-mobile-390px.png")
        await page.screenshot(path=mob_courses_path, full_page=True)
        print(f"Captured: {mob_courses_path}")

        # Desktop 1280px - Course Details Page (Materials Tab)
        await page.set_viewport_size({"width": 1280, "height": 900})
        await page.goto(f"{WEB_URL}/courses/{course_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        desk_detail_path = os.path.join(out_dir, "course-detail-desktop-1280px.png")
        await page.screenshot(path=desk_detail_path, full_page=True)
        print(f"Captured: {desk_detail_path}")

        # Mobile 390px - Course Details Page
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(f"{WEB_URL}/courses/{course_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        mob_detail_path = os.path.join(out_dir, "course-detail-mobile-390px.png")
        await page.screenshot(path=mob_detail_path, full_page=True)
        print(f"Captured: {mob_detail_path}")

        # Desktop 1280px - Requests Tab
        await page.set_viewport_size({"width": 1280, "height": 900})
        await page.goto(f"{WEB_URL}/courses/{course_id}?tab=requests", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        desk_req_path = os.path.join(out_dir, "course-requests-desktop-1280px.png")
        await page.screenshot(path=desk_req_path, full_page=True)
        print(f"Captured: {desk_req_path}")

        # Copy to artifact dir
        for p_path in [desk_courses_path, mob_courses_path, desk_detail_path, mob_detail_path, desk_req_path]:
            shutil.copy(p_path, os.path.join(artifact_dir, os.path.basename(p_path)))

        await browser.close()
    print("All Phase 2 screenshots captured successfully.")

if __name__ == "__main__":
    asyncio.run(setup_and_capture())

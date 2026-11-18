import asyncio
import os
import shutil
import uuid
from playwright.async_api import async_playwright
import httpx
import redis.asyncio as aioredis

API_URL = "http://localhost:8000"
WEB_URL = "http://localhost:3000"


async def setup_and_capture():
    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)
    artifact_dir = r"C:\Users\Vishal\.gemini\antigravity\brain\01d20605-c8dd-48d7-a828-90d34f645bd3"

    # Flush login rate limits so test logins don't get 429
    try:
        r = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
        keys = await r.keys("ratelimit:login:*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass

    client = httpx.AsyncClient(base_url=API_URL, timeout=15.0)

    # 1. Login as admin
    admin_login = await client.post(
        "/auth/login",
        json={"email": "admin@classvault.edu", "password": "AdminPassword123!"},
    )
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Trigger rich audit events
    # Event 1: Create teacher
    teacher_email = f"prof_{uuid.uuid4().hex[:4]}@univ.edu"
    t_res = await client.post(
        "/admin/teachers",
        headers=admin_headers,
        json={"name": "Prof. Margaret Hamilton", "email": teacher_email, "password": "TeacherPassword123!"},
    )

    # Event 2: Student registration & login
    student_email = f"student_{uuid.uuid4().hex[:4]}@univ.edu"
    await client.post(
        "/auth/register",
        json={"name": "Grace Hopper", "email": student_email, "password": "StudentPassword123!"},
    )
    s_login = await client.post(
        "/auth/login",
        json={"email": student_email, "password": "StudentPassword123!"},
    )
    student_token = s_login.json()["access_token"]

    # Event 3: Teacher creates course & unit
    t_login = await client.post("/auth/login", json={"email": teacher_email, "password": "TeacherPassword123!"})
    t_token = t_login.json()["access_token"]
    t_headers = {"Authorization": f"Bearer {t_token}"}

    c_res = await client.post(
        "/courses",
        headers=t_headers,
        json={"name": "Security Architecture & Cryptography", "code": "CS705"},
    )
    course = c_res.json()
    course_id = course["id"]

    u_res = await client.post(
        f"/courses/{course_id}/units",
        headers=t_headers,
        json={"title": "Asymmetric Cryptography"},
    )
    unit = u_res.json()
    unit_id = unit["id"]

    # Event 4: Student requests to join course
    await client.post(
        "/courses/join",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"code": course["join_code"]},
    )

    # Launch Playwright to capture screenshots
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Desktop (1280x800)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # Login as admin in UI
        await page.goto(f"{WEB_URL}/login")
        await page.fill('input[type="email"]', "admin@classvault.edu")
        await page.fill('input[type="password"]', "AdminPassword123!")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/courses")

        # Navigate to Admin Audit Logs
        await page.goto(f"{WEB_URL}/admin/audit")
        await page.wait_for_selector("table tbody tr")
        await page.wait_for_timeout(1000)

        # Click the first "View" details button to expand metadata
        view_buttons = await page.query_selector_all('button:has-text("View")')
        if view_buttons:
            await view_buttons[0].click()
            await page.wait_for_timeout(500)

        desktop_path = os.path.join(out_dir, "audit-desktop-1280px.png")
        await page.screenshot(path=desktop_path)
        print(f"Captured: {desktop_path}")
        await context.close()

        # Mobile (390x844)
        mobile_context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        )
        mobile_page = await mobile_context.new_page()

        # Login as admin in UI
        await mobile_page.goto(f"{WEB_URL}/login")
        await mobile_page.fill('input[type="email"]', "admin@classvault.edu")
        await mobile_page.fill('input[type="password"]', "AdminPassword123!")
        await mobile_page.click('button[type="submit"]')
        await mobile_page.wait_for_url("**/courses")

        # Navigate to Admin Audit Logs
        await mobile_page.goto(f"{WEB_URL}/admin/audit")
        await mobile_page.wait_for_selector("table tbody tr")
        await mobile_page.wait_for_timeout(1000)

        mobile_path = os.path.join(out_dir, "audit-mobile-390px.png")
        await mobile_page.screenshot(path=mobile_path)
        print(f"Captured: {mobile_path}")
        await mobile_context.close()

        await browser.close()

    # Copy screenshots to artifact directory
    artifact_desktop = os.path.join(artifact_dir, "audit-desktop-1280px.png")
    artifact_mobile = os.path.join(artifact_dir, "audit-mobile-390px.png")
    shutil.copy2(desktop_path, artifact_desktop)
    shutil.copy2(mobile_path, artifact_mobile)
    print(f"Copied to artifact dir: {artifact_desktop}")
    print(f"Copied to artifact dir: {artifact_mobile}")


if __name__ == "__main__":
    asyncio.run(setup_and_capture())

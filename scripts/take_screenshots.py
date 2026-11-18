import asyncio
import os
import shutil
from playwright.async_api import async_playwright

async def take_screenshots():
    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)
    artifact_dir = r"C:\Users\Vishal\.gemini\antigravity\brain\01d20605-c8dd-48d7-a828-90d34f645bd3"

    pages = [
        ("styleguide", "http://localhost:3000/styleguide"),
        ("login", "http://localhost:3000/login"),
        ("register", "http://localhost:3000/register"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for name, url in pages:
            # Desktop 1280px
            p_desk = await browser.new_page(viewport={"width": 1280, "height": 900})
            await p_desk.goto(url, wait_until="domcontentloaded")
            await p_desk.wait_for_timeout(1000)
            desk_path = os.path.join(out_dir, f"{name}-desktop-1280px.png")
            await p_desk.screenshot(path=desk_path, full_page=True)
            print(f"Captured: {desk_path}")

            # Mobile 390px
            p_mob = await browser.new_page(viewport={"width": 390, "height": 844})
            await p_mob.goto(url, wait_until="domcontentloaded")
            await p_mob.wait_for_timeout(1000)
            mob_path = os.path.join(out_dir, f"{name}-mobile-390px.png")
            await p_mob.screenshot(path=mob_path, full_page=True)
            print(f"Captured: {mob_path}")

            if os.path.exists(artifact_dir):
                shutil.copy(desk_path, os.path.join(artifact_dir, f"{name}-desktop-1280px.png"))
                shutil.copy(mob_path, os.path.join(artifact_dir, f"{name}-mobile-390px.png"))

        await browser.close()
    print("All screenshots captured and saved to artifact directory.")

if __name__ == "__main__":
    asyncio.run(take_screenshots())

import asyncio
import os
from playwright.async_api import async_playwright

async def take_screenshots():
    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)

    artifact_dir = r"C:\Users\Vishal\.gemini\antigravity\brain\01d20605-c8dd-48d7-a828-90d34f645bd3"

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Desktop 1280px
        page_desktop = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page_desktop.goto("http://localhost:3000/styleguide", wait_until="networkidle")
        path_desktop = os.path.join(out_dir, "styleguide-desktop-1280px.png")
        await page_desktop.screenshot(path=path_desktop, full_page=True)
        print(f"Captured: {path_desktop}")

        # Mobile 390px
        page_mobile = await browser.new_page(viewport={"width": 390, "height": 844})
        await page_mobile.goto("http://localhost:3000/styleguide", wait_until="networkidle")
        path_mobile = os.path.join(out_dir, "styleguide-mobile-390px.png")
        await page_mobile.screenshot(path=path_mobile, full_page=True)
        print(f"Captured: {path_mobile}")

        if os.path.exists(artifact_dir):
            import shutil
            shutil.copy(path_desktop, os.path.join(artifact_dir, "styleguide-desktop-1280px.png"))
            shutil.copy(path_mobile, os.path.join(artifact_dir, "styleguide-mobile-390px.png"))
            print(f"Copied screenshots to artifact directory {artifact_dir}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(take_screenshots())

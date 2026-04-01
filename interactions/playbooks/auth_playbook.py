import asyncio
import time
from playwright.async_api import Page

async def run_login(page: Page, selector: str, credentials: dict) -> int:
    """
    Executes a login interaction and measures how long it takes to reach the post-login state.
    """
    t0 = time.monotonic()
    try:
        # 🧪 Find login fields
        username_el = await page.query_selector('input[type="text"], input[type="email"], input[name*="user" i]')
        password_el = await page.query_selector('input[type="password"]')
        
        if username_el and password_el and credentials:
            await username_el.fill(credentials.get("username", ""))
            await password_el.fill(credentials.get("password", ""))
            await page.keyboard.press("Enter")
            
            # ⏳ Wait for URL to change or network idle
            await page.wait_for_load_state("networkidle", timeout=10000)
        
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"  [WARN] Login playbook failed: {e}")
        return int((time.monotonic() - t0) * 1000)

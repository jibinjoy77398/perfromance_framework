import asyncio
import time
from playwright.async_api import Page

async def run_static(page: Page) -> int:
    """
    Performs scrolling on a static site to test smoothness and render stability.
    """
    t0 = time.monotonic()
    try:
        # 📜 Scroll 50%
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(0.5)
        
        # 📜 Scroll 100%
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)
        
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"  [WARN] Static playbook failed: {e}")
        return int((time.monotonic() - t0) * 1000)

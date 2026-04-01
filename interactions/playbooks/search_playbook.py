import asyncio
import time
from playwright.async_api import Page

async def run_search(page: Page, selector: str) -> int:
    """
    Executes a search interaction and measures how long it takes for results to appear.
    """
    t0 = time.monotonic()
    try:
        # 🧪 Focus and type
        await page.click(selector)
        await page.fill(selector, "test query")
        await page.keyboard.press("Enter")
        
        # ⏳ Wait for the site to settle
        # Some sites might take longer than 5s, but we cap it to 10s for the metric
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        # ⏱️ Measure response time (Enter -> Load Finish)
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"  [WARN] Search playbook failed: {e}")
        return int((time.monotonic() - t0) * 1000)

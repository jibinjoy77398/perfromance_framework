import asyncio
import time
import random
from playwright.async_api import Page

# Diverse set of sample targets to measure "Capability"
SAMPLES = [
    "https://example.com",          # Static/Basic
    "https://opulonapi.com",        # Modern SaaS/React
    "https://github.com",           # Heavy/Complex
    "https://news.ycombinator.com"  # Minimalist
]

async def run_extractor(page: Page, selector: str) -> int:
    """
    Executes a URL-based extraction and measures processing time.
    """
    sample_url = random.choice(SAMPLES)
    t0 = time.monotonic()
    
    try:
        # 🧪 Target the URL input
        await page.click(selector)
        await page.fill(selector, sample_url)
        await page.keyboard.press("Enter")
        
        # ⏳ Wait for processing markers
        # We look for common "Results" indicators: canvas, color grids, or typography sections
        try:
            await page.wait_for_selector('canvas, [class*="palette" i], [class*="result" i], h2:has-text("Results")', timeout=15000)
        except:
            # Fallback to network idle if specific selectors aren't found
            await page.wait_for_load_state("networkidle", timeout=10000)
            
        # ⏱️ Measure total processing time
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"  [WARN] Extractor playbook failed for {sample_url}: {e}")
        return int((time.monotonic() - t0) * 1000)

import asyncio
import time
from dataclasses import dataclass, asdict
from playwright.async_api import async_playwright
from interactions.site_fingerprint import detect_site_type
from interactions.playbooks.search_playbook import run_search
from interactions.playbooks.form_playbook import run_form
from interactions.playbooks.static_playbook import run_static
from interactions.interaction_metrics import capture_post_interaction

from interactions.playbooks.auth_playbook import run_login
from interactions.playbooks.extractor_playbook import run_extractor

@dataclass
class InteractionResult:
    interaction_type: str = "none"
    interaction_time_ms: int = 0
    search_response_ms: int = 0
    js_errors: int = 0
    network_requests: int = 0
    network_bytes_kb: float = 0.0
    # Bulk Stats
    interaction_p95_ms: int = 0
    interaction_avg_ms: float = 0.0
    interaction_count: int = 1

    def as_dict(self):
        return asdict(self)

async def run_interaction(url: str, credentials: dict = None, count: int = 1) -> InteractionResult:
    """
    Launches a dedicated browser session to run site-specific interaction playbooks.
    Supports 'count' iterations for stress testing capability.
    """
    result = InteractionResult(interaction_count=count)
    timings = []
    
    async with async_playwright() as p:
        try:
            # 🚀 Launch shared interaction browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # ⏱️ Initial load for discovery
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 🧠 Fingerprint the site
            signals = await detect_site_type(page)
            result.interaction_type = signals["type"]
            
            # 🩺 Attach reactive health listeners
            metrics = await capture_post_interaction(page)
            
            # 🎭 Execute the corresponding playbook 'count' times
            t0_batch = time.monotonic()
            
            for i in range(count):
                 if count > 1:
                     print(f"    [STRESS] Iteration {i+1}/{count}...")
                 
                 step_time = 0
                 if result.interaction_type == "extractor_site":
                      step_time = await run_extractor(page, signals["selector"])
                 elif result.interaction_type == "search_site":
                      step_time = await run_search(page, signals["selector"])
                 elif result.interaction_type == "auth_site":
                      step_time = await run_login(page, signals["selector"], credentials)
                 elif result.interaction_type == "form_site":
                      step_time = await run_form(page, signals["selector"])
                 else:
                      await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                      await asyncio.sleep(0.5)
                      step_time = 500
                 
                 timings.append(step_time)
                 
                 # Small cooldown to prevent bot detection during bulk runs
                 if count > 1: await asyncio.sleep(0.5)

            # 📊 Aggregate metrics
            result.interaction_time_ms = int((time.monotonic() - t0_batch) * 1000)
            result.js_errors = metrics.get("js_errors", 0)
            result.network_requests = metrics.get("network_requests", 0)
            result.network_bytes_kb = metrics.get("network_bytes_kb", 0.0)
            
            if timings:
                timings.sort()
                result.interaction_avg_ms = round(sum(timings) / len(timings), 2)
                p95_idx = int(len(timings) * 0.95)
                result.interaction_p95_ms = timings[min(p95_idx, len(timings)-1)]
                # Use first timing as standard search_response_ms for compatibility
                result.search_response_ms = timings[0]

            await browser.close()
        except Exception as e:
            print(f"  [WARN] Interaction sequence failed for {url}: {e}")
            pass

    return result

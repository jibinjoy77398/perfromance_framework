"""
test_breakpoint.py — Ramps concurrent users 1→2→5→10→20→50.
Detects the exact step where the site breaks and the reason why.
"""
from __future__ import annotations
import asyncio
import time
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from utils.threshold_evaluator import load_thresholds

pytestmark = pytest.mark.asyncio

RAMP_STEPS = [
    int(x) for x in os.environ.get("PERF_RAMP_STEPS", "1,2,5,10,20").split(",")
]
REQUEST_TIMEOUT = int(os.environ.get("PERF_TIMEOUT_MS", "30000"))


async def _user_session(url: str, creds: dict | None,
                        semaphore: asyncio.Semaphore) -> dict:
    """One user session → returns timing + error info."""
    result = {"error": None, "load_time": 0, "ttfb": 0, "lcp": 0, "status": "ok"}
    async with semaphore:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True, args=["--disable-extensions", "--no-sandbox"]
                )
                ctx = await browser.new_context(ignore_https_errors=True)
                page = await ctx.new_page()

                t0 = time.monotonic()
                resp = await page.goto(url, wait_until="domcontentloaded",
                                       timeout=REQUEST_TIMEOUT)
                if resp and resp.status >= 400:
                    result["error"] = f"HTTP {resp.status}"
                    result["status"] = "http_error"
                else:
                    await page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT)
                    result["load_time"] = (time.monotonic() - t0) * 1000
                    perf = await page.evaluate("""
                        () => {
                            const n = performance.getEntriesByType('navigation')[0] || {};
                            const paints = {};
                            performance.getEntriesByType('paint').forEach(e => paints[e.name] = e.startTime);
                            return {
                                ttfb: n.responseStart - n.requestStart,
                                lcp: window.__lcp || 0,
                            };
                        }
                    """)
                    result["ttfb"] = perf.get("ttfb", 0)
                    result["lcp"] = perf.get("lcp", 0)
                await browser.close()
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
            result["status"] = "timeout"
        except Exception as e:
            result["error"] = str(e)
            result["status"] = "exception"
    return result


async def _run_level(url: str, creds: dict | None, n_users: int) -> dict:
    """Run n_users concurrently and aggregate results."""
    sem = asyncio.Semaphore(n_users)
    tasks = [_user_session(url, creds, sem) for _ in range(n_users)]
    results = await asyncio.gather(*tasks)

    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] != "ok"]
    error_rate = (len(failed) / n_users) * 100

    load_times = sorted(r["load_time"] for r in ok) if ok else [0]
    p95_idx = int(len(load_times) * 0.95)
    p95 = load_times[min(p95_idx, len(load_times) - 1)]
    avg_ttfb = (sum(r["ttfb"] for r in ok) / len(ok)) if ok else 0
    avg_lcp = (sum(r["lcp"] for r in ok) / len(ok)) if ok else 0

    error_reasons: dict[str, int] = {}
    for r in failed:
        reason = r.get("error", "unknown")
        error_reasons[reason] = error_reasons.get(reason, 0) + 1

    return {
        "users": n_users,
        "ok": len(ok),
        "failed": len(failed),
        "error_rate_pct": round(error_rate, 1),
        "p95_load_time": round(p95, 1),
        "avg_ttfb": round(avg_ttfb, 1),
        "avg_lcp": round(avg_lcp, 1),
        "error_reasons": error_reasons,
    }


@pytest.mark.asyncio
async def test_breakpoint_finder(site):
    """
    Ramp concurrent users step by step.
    Detect and report the exact level where the site breaks.
    """
    t = load_thresholds()
    url = site["url"]
    creds = site.get("credentials")
    error_threshold = t["error_rate_pct"]
    p95_threshold = t["p95_load_time"]

    breakpoint_level = None
    breakpoint_reason = None
    all_levels = []

    print(f"\n[{site['name']}] Breakpoint Finder — ramping users:")
    print(f"{'Users':>6}  {'OK':>5}  {'Fail':>5}  {'Err%':>6}  "
          f"{'p95 Load':>10}  {'Avg TTFB':>10}  Reason")
    print("-" * 70)

    for step in RAMP_STEPS:
        level = await _run_level(url, creds, step)
        all_levels.append(level)

        reason = ""
        broke = False
        if level["error_rate_pct"] > error_threshold:
            broke = True
            reasons = level["error_reasons"]
            reason = ", ".join(f"{k}×{v}" for k, v in reasons.items())
        elif level["p95_load_time"] > p95_threshold:
            broke = True
            reason = f"p95 load {level['p95_load_time']}ms > {p95_threshold}ms"

        status_flag = "❌ BREAK" if broke else "✅"
        print(f"{step:>6}  {level['ok']:>5}  {level['failed']:>5}  "
              f"{level['error_rate_pct']:>5.1f}%  "
              f"{level['p95_load_time']:>9.0f}ms  "
              f"{level['avg_ttfb']:>9.0f}ms  {status_flag} {reason}")

        if broke and breakpoint_level is None:
            breakpoint_level = step
            breakpoint_reason = reason

    if breakpoint_level:
        pytest.fail(
            f"[{site['name']}] Site breaks at {breakpoint_level} concurrent users. "
            f"Reason: {breakpoint_reason}"
        )
    else:
        print(f"\n  ✅ Site held under {RAMP_STEPS[-1]} concurrent users.")

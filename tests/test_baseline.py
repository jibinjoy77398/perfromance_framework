"""
test_baseline.py — N concurrent browser sessions measuring all Core Web Vitals.
Computes p50, p95, min, max, stddev per metric to reveal stability.
"""
from __future__ import annotations
import asyncio
import statistics
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from pages.base_page import BasePage
from utils.threshold_evaluator import load_thresholds

pytestmark = pytest.mark.asyncio

CONCURRENT_RUNS = int(os.environ.get("PERF_CONCURRENT", "5"))


async def _single_run(url: str, creds: dict | None,
                      login_url: str | None = None) -> dict:
    """One isolated browser session → returns metrics dict."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--disable-extensions", "--no-sandbox"]
        )
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        bp = BasePage(page, url, login_url=login_url)
        await bp.setup()
        await bp.navigate()
        if creds:
            await bp.login(creds["username"], creds["password"])
            await bp.navigate()
        await bp.scroll_to_bottom()
        metrics = await bp.get_metrics()
        await browser.close()
        return metrics


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    data_sorted = sorted(data)
    index = int(len(data_sorted) * pct / 100)
    return data_sorted[min(index, len(data_sorted) - 1)]


async def _gather_baseline(site: dict, n: int = CONCURRENT_RUNS) -> dict:
    """Run N concurrent sessions and return aggregated statistics."""
    url = site["url"]
    creds = site.get("credentials")
    login_url = site.get("login_url")
    tasks = [_single_run(url, creds, login_url=login_url) for _ in range(n)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    valid = [r for r in results if isinstance(r, dict)]
    errors = [r for r in results if isinstance(r, Exception)]

    if not valid:
        raise RuntimeError(f"All {n} baseline runs failed: {errors}")

    vitals = ["fcp", "lcp", "ttfb", "cls", "tbt", "load_time", "dom_content_loaded"]
    stats: dict[str, dict] = {}
    for v in vitals:
        values = [r.get(v, 0) for r in valid]
        stats[v] = {
            "p50": round(_percentile(values, 50), 2),
            "p95": round(_percentile(values, 95), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "stddev": round(statistics.stdev(values) if len(values) > 1 else 0, 2),
            "runs": len(valid),
            "errors": len(errors),
        }
    return stats


@pytest.mark.asyncio
async def test_baseline_p95_load_time(site):
    """p95 load time across N concurrent runs must be under threshold."""
    t = load_thresholds()
    stats = await _gather_baseline(site)
    lcp_p95 = stats["lcp"]["p95"]
    load_p95 = stats["load_time"]["p95"]
    print(f"\n[{site['name']}] Baseline stats across {stats['lcp']['runs']} runs:")
    for metric, s in stats.items():
        print(f"  {metric:20s}  p50={s['p50']:8.1f}  p95={s['p95']:8.1f}  "
              f"stddev={s['stddev']:7.1f}  min={s['min']:8.1f}  max={s['max']:8.1f}")

    assert load_p95 <= t["p95_load_time"], (
        f"[{site['name']}] p95 load_time {load_p95:.0f}ms > threshold {t['p95_load_time']}ms"
    )


@pytest.mark.asyncio
async def test_baseline_stddev_stability(site):
    """StdDev of load time must be low (server is consistent)."""
    t = load_thresholds()
    stats = await _gather_baseline(site)
    stddev = stats["load_time"]["stddev"]
    assert stddev <= t["stddev_load_time"], (
        f"[{site['name']}] load_time stddev {stddev:.0f}ms > threshold {t['stddev_load_time']}ms — "
        f"server performance is inconsistent"
    )

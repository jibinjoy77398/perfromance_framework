"""
test_network_stress.py — Measures Core Web Vitals under 4 network profiles:
Broadband → 4G → Fast 3G → Slow 3G (via CDP Network.emulateNetworkConditions).
"""
from __future__ import annotations
import asyncio
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from pages.base_page import BasePage
from utils.threshold_evaluator import load_thresholds

pytestmark = pytest.mark.asyncio

NETWORK_PROFILES = {
    "Broadband": {"offline": False, "downloadThroughput": 5_000_000,
                  "uploadThroughput": 1_250_000, "latency": 0},
    "4G":        {"offline": False, "downloadThroughput": 2_500_000,
                  "uploadThroughput": 1_250_000, "latency": 20},
    "Fast 3G":   {"offline": False, "downloadThroughput": 187_500,
                  "uploadThroughput": 93_750,    "latency": 40},
    "Slow 3G":   {"offline": False, "downloadThroughput": 62_500,
                  "uploadThroughput": 62_500,    "latency": 400},
}


async def _run_with_profile(url: str, creds: dict | None,
                             profile_name: str, profile_settings: dict,
                             login_url: str | None = None) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--disable-extensions", "--no-sandbox"]
        )
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()

        # Apply network throttling via CDP
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Network.enable")
        await cdp.send("Network.emulateNetworkConditions", profile_settings)

        bp = BasePage(page, url, login_url=login_url)
        await bp.setup()
        await bp.navigate()
        if creds:
            await bp.login(creds["username"], creds["password"])
            await bp.navigate()
        metrics = await bp.get_metrics()
        await cdp.detach()
        await browser.close()
        metrics["profile"] = profile_name
        return metrics


@pytest.mark.asyncio
async def test_network_stress(site):
    """
    Run the site under all 4 network profiles. Report metrics per profile.
    Fail if even Broadband breaks thresholds — warns for slower profiles.
    """
    t = load_thresholds()
    url = site["url"]
    creds = site.get("credentials")
    login_url = site.get("login_url")

    tasks = {
        name: _run_with_profile(url, creds, name, settings, login_url=login_url)
        for name, settings in NETWORK_PROFILES.items()
    }
    # Run profiles sequentially to avoid port conflicts
    results: dict[str, dict] = {}
    for name, coro in tasks.items():
        results[name] = await coro

    print(f"\n[{site['name']}] Network Stress Results:")
    header = f"{'Profile':12s}  {'FCP':>8s}  {'LCP':>8s}  {'TTFB':>8s}  {'Load':>8s}  {'CLS':>6s}"
    print(header)
    print("-" * len(header))
    for profile, m in results.items():
        print(f"{profile:12s}  {m.get('fcp',0):8.0f}  {m.get('lcp',0):8.0f}  "
              f"{m.get('ttfb',0):8.0f}  {m.get('load_time',0):8.0f}  {m.get('cls',0):6.3f}")

    # Hard fail only on Broadband
    broadband = results["Broadband"]
    assert broadband["load_time"] <= t["load_time"], (
        f"[{site['name']}] Broadband load_time {broadband['load_time']:.0f}ms "
        f"> threshold {t['load_time']}ms"
    )
    assert broadband["lcp"] <= t["lcp"], (
        f"[{site['name']}] Broadband LCP {broadband['lcp']:.0f}ms "
        f"> threshold {t['lcp']}ms"
    )

"""
test_page_load.py — Core page load metrics: FCP, LCP, TTFB, TTI, load time.
"""
import pytest
import pytest_asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.base_page import BasePage
from utils.threshold_evaluator import evaluate, load_thresholds

pytestmark = pytest.mark.asyncio


async def _run(site, page) -> dict:
    bp = BasePage(page, site["url"], login_url=site.get("login_url"))
    await bp.setup()
    await bp.navigate()
    creds = site.get("credentials")
    if creds:
        await bp.login(creds["username"], creds["password"])
        await bp.navigate()  # measure post-login load
    await bp.scroll_to_bottom()
    return await bp.get_metrics()


@pytest.mark.asyncio
async def test_fcp(site, page):
    """First Contentful Paint must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["fcp"] <= t["fcp"], (
        f"[{site['name']}] FCP {metrics['fcp']:.0f}ms exceeds threshold {t['fcp']}ms"
    )


@pytest.mark.asyncio
async def test_lcp(site, page):
    """Largest Contentful Paint must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["lcp"] <= t["lcp"], (
        f"[{site['name']}] LCP {metrics['lcp']:.0f}ms exceeds threshold {t['lcp']}ms"
    )


@pytest.mark.asyncio
async def test_ttfb(site, page):
    """Time to First Byte must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["ttfb"] <= t["ttfb"], (
        f"[{site['name']}] TTFB {metrics['ttfb']:.0f}ms exceeds threshold {t['ttfb']}ms"
    )


@pytest.mark.asyncio
async def test_load_time(site, page):
    """Total page load time must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["load_time"] <= t["load_time"], (
        f"[{site['name']}] load_time {metrics['load_time']:.0f}ms exceeds {t['load_time']}ms"
    )


@pytest.mark.asyncio
async def test_dom_content_loaded(site, page):
    """DOMContentLoaded event must fire under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["dom_content_loaded"] <= t["dom_content_loaded"], (
        f"[{site['name']}] DCL {metrics['dom_content_loaded']:.0f}ms exceeds {t['dom_content_loaded']}ms"
    )

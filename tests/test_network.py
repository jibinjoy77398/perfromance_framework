"""
test_network.py — Network health: failed requests, slow requests, HTTP errors.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.base_page import BasePage
from utils.threshold_evaluator import load_thresholds

pytestmark = pytest.mark.asyncio


async def _run(site, page) -> dict:
    bp = BasePage(page, site["url"], login_url=site.get("login_url"))
    await bp.setup()
    await bp.navigate()
    creds = site.get("credentials")
    if creds:
        await bp.login(creds["username"], creds["password"])
        await bp.navigate()
    return await bp.get_metrics()


@pytest.mark.asyncio
async def test_no_failed_requests(site, page):
    """No network requests should fail (4xx/5xx or connection error)."""
    metrics = await _run(site, page)
    t = load_thresholds()
    failed = metrics["failed_requests"]
    assert failed <= t["failed_requests"], (
        f"[{site['name']}] {failed} failed request(s): {metrics.get('failed_urls', [])}"
    )


@pytest.mark.asyncio
async def test_slow_requests(site, page):
    """Number of slow requests (>1 s) must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    slow = metrics["slow_requests"]
    assert slow <= t["slow_requests"], (
        f"[{site['name']}] {slow} slow request(s) exceed threshold of {t['slow_requests']}"
    )

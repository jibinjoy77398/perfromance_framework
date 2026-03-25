"""
test_resources.py — Resource budget: count, size, blocking JS/CSS.
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
async def test_resource_count(site, page):
    """Total number of network requests must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["resource_count"] <= t["resource_count"], (
        f"[{site['name']}] {metrics['resource_count']} requests exceed threshold {t['resource_count']}"
    )


@pytest.mark.asyncio
async def test_total_size(site, page):
    """Total page weight (all resources) must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    size = metrics["total_resource_size_kb"]
    assert size <= t["total_resource_size_kb"], (
        f"[{site['name']}] Page size {size:.1f} KB exceeds threshold {t['total_resource_size_kb']} KB"
    )

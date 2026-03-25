"""
test_memory.py — JavaScript heap usage during page load.
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
    await bp.scroll_to_bottom()
    return await bp.get_metrics()


@pytest.mark.asyncio
async def test_js_heap(site, page):
    """JS heap memory usage must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    heap = metrics["js_heap_used_mb"]
    assert heap <= t["js_heap_used_mb"], (
        f"[{site['name']}] JS heap {heap:.1f} MB exceeds threshold {t['js_heap_used_mb']} MB"
    )

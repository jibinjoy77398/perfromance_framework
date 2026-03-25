"""
test_interactions.py — Interaction quality: CLS, TBT, long tasks.
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
async def test_cls(site, page):
    """Cumulative Layout Shift must be under threshold (0.1 = good)."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["cls"] <= t["cls"], (
        f"[{site['name']}] CLS {metrics['cls']:.3f} exceeds threshold {t['cls']}"
    )


@pytest.mark.asyncio
async def test_tbt(site, page):
    """Total Blocking Time must be under threshold."""
    metrics = await _run(site, page)
    t = load_thresholds()
    assert metrics["tbt"] <= t["tbt"], (
        f"[{site['name']}] TBT {metrics['tbt']:.0f}ms exceeds threshold {t['tbt']}ms"
    )

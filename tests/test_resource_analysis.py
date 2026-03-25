"""
test_resource_analysis.py — Groups all page resources by type.
Reports slowest and heaviest requests, flags uncompressed/uncached resources.
"""
from __future__ import annotations
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from pages.base_page import BasePage

pytestmark = pytest.mark.asyncio

TOP_N = 10  # How many items in slowest/heaviest lists


async def _collect_resources(site: dict) -> tuple[list[dict], dict]:
    """Navigate the site and collect all request details including timing."""
    url = site["url"]
    creds = site.get("credentials")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--disable-extensions", "--no-sandbox"]
        )
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        requests: list[dict] = []
        timing_map: dict[str, float] = {}

        def on_request(req):
            requests.append({
                "url": req.url,
                "resource_type": req.resource_type,
                "size_bytes": 0,
                "duration_ms": 0,
                "status": 0,
                "is_https": req.url.startswith("https://"),
                "failed": False,
            })

        def on_response(resp):
            for r in reversed(requests):
                if r["url"] == resp.url and r["status"] == 0:
                    r["status"] = resp.status
                    cl = resp.headers.get("content-length", "0")
                    try:
                        r["size_bytes"] = int(cl)
                    except Exception:
                        r["size_bytes"] = 0
                    # Cache header check
                    cc = resp.headers.get("cache-control", "")
                    r["has_cache"] = bool(cc and "no-store" not in cc and "no-cache" not in cc)
                    # Content-encoding
                    enc = resp.headers.get("content-encoding", "")
                    r["compressed"] = enc in ("gzip", "br", "zstd", "deflate")
                    break

        def on_failed(req):
            for r in reversed(requests):
                if r["url"] == req.url:
                    r["failed"] = True
                    break

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_failed)

        bp = BasePage(page, url, login_url=site.get("login_url"))
        await bp.setup()
        await bp.navigate()
        if creds:
            await bp.login(creds["username"], creds["password"])
            await bp.navigate()

        # Collect resource timing from JS for actual duration
        await page.wait_for_load_state("networkidle", timeout=30_000)
        timing_entries = await page.evaluate("""
            () => performance.getEntriesByType('resource').map(e => ({
                url: e.name,
                duration: e.duration,
                transferSize: e.transferSize,
            }))
        """)
        for entry in timing_entries:
            timing_map[entry["url"]] = entry["duration"]

        for r in requests:
            if r["url"] in timing_map:
                r["duration_ms"] = round(timing_map[r["url"]], 2)
            if r["size_bytes"] == 0 and r["url"] in timing_map:
                # Try transfer size from timing API
                for te in timing_entries:
                    if te["url"] == r["url"] and te["transferSize"] > 0:
                        r["size_bytes"] = te["transferSize"]
                        break

        await browser.close()

    # Group by resource type
    grouped: dict[str, dict] = {}
    for r in requests:
        t = r["resource_type"] or "other"
        if t not in grouped:
            grouped[t] = {"count": 0, "total_size_kb": 0.0,
                          "total_duration_ms": 0.0, "items": []}
        grouped[t]["count"] += 1
        grouped[t]["total_size_kb"] += r["size_bytes"] / 1024
        grouped[t]["total_duration_ms"] += r["duration_ms"]
        grouped[t]["items"].append(r)
    for g in grouped.values():
        g["total_size_kb"] = round(g["total_size_kb"], 2)
        g["avg_duration_ms"] = round(
            g["total_duration_ms"] / g["count"] if g["count"] else 0, 2
        )

    return requests, grouped


@pytest.mark.asyncio
async def test_resource_analyzer(site):
    """Analyze resources — always passes, prints detailed breakdown."""
    requests, grouped = await _collect_resources(site)

    print(f"\n[{site['name']}] ── Resource Analysis ──")
    print(f"\n{'Type':15s}  {'Count':>6}  {'Total Size':>12}  {'Avg Duration':>14}")
    print("-" * 55)
    for rtype, data in sorted(grouped.items(), key=lambda x: -x[1]["total_size_kb"]):
        print(f"{rtype:15s}  {data['count']:>6}  "
              f"{data['total_size_kb']:>10.1f} KB  "
              f"{data['avg_duration_ms']:>12.0f} ms")

    # Top N slowest
    slowest = sorted(
        [r for r in requests if not r["failed"]],
        key=lambda x: x["duration_ms"], reverse=True
    )[:TOP_N]
    print(f"\n  🐢 Top {TOP_N} Slowest Requests:")
    for i, r in enumerate(slowest, 1):
        print(f"  {i:>2}. {r['duration_ms']:>8.0f} ms  [{r['resource_type']:10s}]  "
              f"{r['url'][:80]}")

    # Top N heaviest
    heaviest = sorted(
        [r for r in requests if not r["failed"]],
        key=lambda x: x["size_bytes"], reverse=True
    )[:TOP_N]
    print(f"\n  🐘 Top {TOP_N} Heaviest Requests:")
    for i, r in enumerate(heaviest, 1):
        size_kb = r["size_bytes"] / 1024
        print(f"  {i:>2}. {size_kb:>8.1f} KB  [{r['resource_type']:10s}]  "
              f"{r['url'][:80]}")

    # Flag issues
    insecure = [r for r in requests if not r["is_https"]]
    uncompressed = [r for r in requests
                    if not r.get("compressed") and r.get("resource_type") in
                    ("script", "stylesheet", "document", "xhr", "fetch")]
    uncached = [r for r in requests if not r.get("has_cache")]

    if insecure:
        print(f"\n  ⚠️  {len(insecure)} insecure (HTTP) request(s)")
    if uncompressed:
        print(f"  ⚠️  {len(uncompressed)} uncompressed text resource(s)")
    if uncached:
        print(f"  ⚠️  {len(uncached)} resource(s) missing cache headers")

    # Always passes — this is an informational analysis test
    assert True

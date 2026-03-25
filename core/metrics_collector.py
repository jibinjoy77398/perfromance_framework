"""
Metrics Collector — extracts all performance data from a Playwright Page.
Uses Navigation Timing API, PerformanceObserver entries, and CDP.
"""
from __future__ import annotations
import json
from playwright.async_api import Page


_PERF_SCRIPT = """
() => {
    const nav   = performance.getEntriesByType('navigation')[0] || {};
    const paints = {};
    performance.getEntriesByType('paint').forEach(e => { paints[e.name] = e.startTime; });

    // Collect LCP via PerformanceObserver stored on window (injected beforehand)
    const lcp   = window.__lcp  || 0;
    const cls   = window.__cls  || 0;
    const tbt   = window.__tbt  || 0;
    const inp   = window.__inp  || 0;

    return {
        ttfb:               nav.responseStart - nav.requestStart,
        dom_content_loaded: nav.domContentLoadedEventEnd - nav.startTime,
        load_time:          nav.loadEventEnd - nav.startTime,
        fcp:                paints['first-contentful-paint'] || 0,
        lcp:                lcp,
        cls:                cls,
        tbt:                tbt,
        inp:                inp,
        dom_elements:       document.querySelectorAll('*').length,
    };
}
"""

_OBSERVER_SCRIPT = """
() => {
    window.__lcp = 0; window.__cls = 0; window.__tbt = 0; window.__inp = 0;
    window.__longTasks = [];

    // LCP
    try {
        new PerformanceObserver(list => {
            const entries = list.getEntries();
            if (entries.length) window.__lcp = entries[entries.length - 1].startTime;
        }).observe({ type: 'largest-contentful-paint', buffered: true });
    } catch(e) {}

    // CLS
    try {
        new PerformanceObserver(list => {
            for (const e of list.getEntries()) {
                if (!e.hadRecentInput) window.__cls += e.value;
            }
        }).observe({ type: 'layout-shift', buffered: true });
    } catch(e) {}

    // Long tasks → TBT
    try {
        new PerformanceObserver(list => {
            for (const e of list.getEntries()) {
                const blocking = e.duration - 50;
                if (blocking > 0) window.__tbt += blocking;
                window.__longTasks.push({ duration: e.duration, start: e.startTime });
            }
        }).observe({ type: 'longtask', buffered: true });
    } catch(e) {}

    // INP (interaction next paint — best effort)
    try {
        new PerformanceObserver(list => {
            for (const e of list.getEntries()) {
                if (e.duration > window.__inp) window.__inp = e.duration;
            }
        }).observe({ type: 'event', buffered: true, durationThreshold: 16 });
    } catch(e) {}
}
"""


class MetricsCollector:
    def __init__(self, page: Page):
        self.page = page
        self._network_requests: list[dict] = []
        self._failed: list[dict] = []
        self._page_errors: list[str] = []
        self._setup_done = False

    async def setup(self) -> None:
        """Must be called once before navigating the page."""
        if self._setup_done:
            return
        # Inject observer script before every navigation
        await self.page.add_init_script(_OBSERVER_SCRIPT)

        # Track network requests
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("requestfailed", self._on_failed)
        self.page.on("pageerror", lambda e: self._page_errors.append(str(e)))
        self._setup_done = True

    def _on_request(self, req) -> None:
        self._network_requests.append({
            "url": req.url,
            "resource_type": req.resource_type,
            "start": None,
            "size": 0,
            "duration": 0,
            "status": 0,
            "failed": False,
        })

    def _on_response(self, resp) -> None:
        url = resp.url
        for r in reversed(self._network_requests):
            if r["url"] == url and r["status"] == 0:
                r["status"] = resp.status
                try:
                    ct = resp.headers.get("content-length")
                    r["size"] = int(ct) if ct else 0
                except Exception:
                    r["size"] = 0
                break

    def _on_failed(self, req) -> None:
        self._failed.append({"url": req.url, "reason": req.failure})
        for r in reversed(self._network_requests):
            if r["url"] == req.url:
                r["failed"] = True
                break

    async def collect(self) -> dict:
        """Wait a moment for observers, then harvest all metrics."""
        await self.page.wait_for_load_state("networkidle", timeout=30_000)
        # Small extra wait so PerformanceObserver fires for LCP/CLS
        await self.page.wait_for_timeout(1500)

        core = await self.page.evaluate(_PERF_SCRIPT)

        # CDP heap stats
        cdp = await self.page.context.new_cdp_session(self.page)
        try:
            heap_raw = await cdp.send("Runtime.getHeapUsage")
            js_heap_used_mb = round(heap_raw.get("usedSize", 0) / 1_048_576, 2)
        except Exception:
            js_heap_used_mb = 0
        finally:
            await cdp.detach()

        # Resource breakdown
        resources = self._summarize_resources()

        slow_threshold_ms = 1000
        slow_requests = [
            r for r in self._network_requests
            if r.get("duration", 0) > slow_threshold_ms
        ]

        return {
            **core,
            "js_heap_used_mb": js_heap_used_mb,
            "resource_count": len(self._network_requests),
            "total_resource_size_kb": round(
                sum(r["size"] for r in self._network_requests) / 1024, 2
            ),
            "failed_requests": len(self._failed),
            "failed_urls": [f["url"] for f in self._failed],
            "slow_requests": len(slow_requests),
            "page_errors": self._page_errors,
            "resources_by_type": resources,
            "all_requests": self._network_requests,
        }

    def _summarize_resources(self) -> dict:
        grouped: dict[str, dict] = {}
        for r in self._network_requests:
            t = r["resource_type"] or "other"
            if t not in grouped:
                grouped[t] = {"count": 0, "total_size_kb": 0, "requests": []}
            grouped[t]["count"] += 1
            grouped[t]["total_size_kb"] += r["size"] / 1024
            grouped[t]["requests"].append(r)
        for t in grouped:
            grouped[t]["total_size_kb"] = round(grouped[t]["total_size_kb"], 2)
        return grouped

    def reset(self) -> None:
        self._network_requests.clear()
        self._failed.clear()
        self._page_errors.clear()

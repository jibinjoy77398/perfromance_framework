"""
Metrics Collector — extracts all performance data from a Playwright Page.
Uses Navigation Timing API, PerformanceObserver entries, and CDP.
"""
from __future__ import annotations
from playwright.async_api import Page


# FIX: Bug 1 - FCP: read from paint entries (already correct approach)
# FIX: Bug 3 - dom_content_loaded and load_time: subtract nav.startTime so
#              values are durations (ms since navigation), not raw timestamps.
#              Before fix: nav.loadEventEnd returned e.g. 1_700_000_000_000ms (epoch).
#              After fix:  nav.loadEventEnd - nav.startTime returns e.g. 3200ms (correct).
_PERF_SCRIPT = """
() => {
    return new Promise((resolve) => {
        const nav = performance.getEntriesByType('navigation')[0] || {};
        const zeroPoint = nav.fetchStart || 0;

        // Collect what we have immediately
        const paints = performance.getEntriesByType('paint');
        const fcpEntry = paints.find(e => e.name === 'first-contentful-paint');
        const fcp = fcpEntry ? Math.round(fcpEntry.startTime) : 0;

        const finalize = () => {
            let lcp = window.__lcp || 0;
            // FALLBACK: If LCP is still 0 after load, use loadEventEnd - fetchStart as proxy
            if (lcp === 0 && nav.loadEventEnd) {
                lcp = nav.loadEventEnd - nav.fetchStart;
            }

            const cls = window.__cls !== undefined ? parseFloat((window.__cls).toFixed(4)) : 0;
            const tbt = Math.round(window.__tbt || 0);
            const inp = Math.round(window.__inp || 0);
            const ttfb = nav.responseStart && nav.fetchStart ? Math.round(nav.responseStart - nav.fetchStart) : 0;
            const dom_content_loaded = nav.domContentLoadedEventEnd && nav.fetchStart ? Math.round(nav.domContentLoadedEventEnd - nav.fetchStart) : 0;
            const load_time = nav.loadEventEnd && nav.fetchStart ? Math.round(nav.loadEventEnd - nav.fetchStart) : 0;
            
            const render_blocking_count = document.querySelectorAll('link[rel="stylesheet"]:not([media="print"]), script:not([async]):not([defer])').length;
            const headResources = performance.getEntriesByType('resource').filter(r => 
                (r.name.endsWith('.css') || r.name.endsWith('.js')) && 
                (document.head.querySelector(`[href*="${r.name.split('/').pop()}"], [src*="${r.name.split('/').pop()}"]`))
            );
            const render_blocking_size = headResources.reduce((acc, r) => acc + (r.encodedBodySize || 0), 0);

            resolve({
                fcp: fcp || 0,
                lcp: lcp || 0,
                cls,
                tbt,
                inp,
                ttfb,
                dom_content_loaded,
                load_time,
                dom_elements: document.querySelectorAll('*').length,
                render_blocking_count,
                render_blocking_size_kb: Math.round(render_blocking_size / 1024)
            });
        };

        if (document.readyState === 'complete') {
            setTimeout(finalize, 500);
        } else {
            window.addEventListener('load', () => setTimeout(finalize, 500), { once: true });
        }
    });
}
"""

# Injected before every navigation via add_init_script — runs before any JS on the page.
# This is the ONLY correct way to capture LCP/CLS/TBT — they must be observed from the start.
_OBSERVER_SCRIPT = """
() => {
    window.__lcp = 0;
    window.__cls = 0;
    window.__tbt = 0;
    window.__inp = 0;
    window.__longTasks = [];

    // FIX 1: LCP properly waiting for interaction or visibility change
    const lcpObserver = new PerformanceObserver((entryList) => {
      const entries = entryList.getEntries();
      entries.forEach((entry) => {
        if (entry.startTime > window.__lcp) {
          window.__lcp = entry.startTime;
        }
      });
    });
    lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });

    // Disconnect only on user interaction or page hide — not on load
    ['keydown', 'click', 'scroll', 'touchstart'].forEach((event) => {
      window.addEventListener(event, () => {
        lcpObserver.disconnect();
      }, { once: true, passive: true });
    });

    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        lcpObserver.disconnect();
      }
    });

    // CLS — cumulative layout shift (unchanged per user request)
    try {
        new PerformanceObserver(list => {
            for (const e of list.getEntries()) {
               if (!e.hadRecentInput) window.__cls += e.value;
            }
        }).observe({ type: 'layout-shift', buffered: true });
    } catch(e) {}

    // FIX 3: TBT accumulating blocking time correctly (>50ms)
    new PerformanceObserver((entryList) => {
      entryList.getEntries().forEach((entry) => {
        if (entry.duration > 50) {
          window.__tbt += entry.duration - 50;
        }
      });
    }).observe({ type: 'longtask', buffered: true });

    // INP (unchanged per user request)
    try {
        new PerformanceObserver(list => {
            for (const e of list.getEntries()) {
                if (e.duration > window.__inp) window.__inp = e.duration;
            }
        }).observe({ type: 'event', buffered: true, durationThreshold: 0 }); // FIX: INP threshold 0 captures all interaction events
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
        # add_init_script ensures _OBSERVER_SCRIPT runs before page JS on every navigation
        await self.page.add_init_script(_OBSERVER_SCRIPT)

        self.page.on("request",       self._on_request)
        self.page.on("response",      self._on_response)
        self.page.on("requestfailed", self._on_failed)
        self.page.on("pageerror",     lambda e: self._page_errors.append(str(e)))
        self._setup_done = True

    async def apply_fast_3g_throttling(self) -> None:
        """Establishes a CDPSession to simulate Fast 3G: 150ms latency, 1.6Mbps down, 750Kbps up."""
        cdp = await self.page.context.new_cdp_session(self.page)
        await cdp.send("Network.enable")
        await cdp.send("Network.emulateNetworkConditions", {
            "offline": False,
            "latency": 150,
            "downloadThroughput": 1.6 * 1024 * 1024 / 8, # 1.6 Mbps
            "uploadThroughput": 750 * 1024 / 8,          # 750 Kbps
        })
        print("  📡 Fast 3G Throttling Applied (150ms / 1.6Mbps)")

    # NEW: interaction simulation for TBT/INP accuracy (Improvement 1)
    async def simulate_interactions(self) -> None:
        """Simulates synthetic user behavior to trigger TBT and INP metrics."""
        original_url = self.page.url
        try:
            # 1. Click centre to trigger INP
            viewport = self.page.viewport_size or {"width": 1280, "height": 720}
            await self.page.mouse.click(viewport["width"] / 2, viewport["height"] / 2)
            await self.page.wait_for_timeout(300)

            # 2. Key interactions
            for _ in range(3):
                await self.page.keyboard.press("Tab")
                await self.page.wait_for_timeout(100)

            # 3. Hover/Move interactions
            await self.page.mouse.move(viewport["width"] * 0.25, viewport["height"] * 0.5)
            await self.page.mouse.move(viewport["width"] * 0.75, viewport["height"] * 0.5)
            await self.page.wait_for_timeout(200)

            # Navigation Protection
            if self.page.url != original_url:
                await self.page.go_back()
                await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass # Silent pass if interaction fails

    def _on_request(self, req) -> None:
        self._network_requests.append({
            "url":           req.url,
            "resource_type": req.resource_type,
            "size":          0,
            "duration":      0,
            "status":        0,
            "failed":        False,
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
        """Wait for page to settle, then harvest all metrics."""
        # FIX: Bug 1 - Cap networkidle wait at 10s (not 15s) to avoid inflating
        #              all timing metrics on sites with background polling.
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        # NEW: interaction simulation for TBT/INP accuracy
        await self.simulate_interactions()

        # Synchronization: Reduced wait time (1s is usually enough for throttled paint events)
        await self.page.wait_for_timeout(1000)

        # Read all metrics — window.__lcp/cls/tbt/inp already populated by init script
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

        resources = self._summarize_resources()

        slow_threshold_ms = 1000
        slow_requests = [
            r for r in self._network_requests
            if r.get("duration", 0) > slow_threshold_ms
        ]

        return {
            **core,
            "js_heap_used_mb":        js_heap_used_mb,
            "resource_count":         len(self._network_requests),
            "total_resource_size_kb": round(
                sum(r["size"] for r in self._network_requests) / 1024, 2
            ),
            "failed_requests":        len(self._failed),
            "failed_urls":            [f["url"] for f in self._failed],
            "slow_requests":          len(slow_requests),
            "page_errors":            self._page_errors,
            "resources_by_type":      resources,
            "all_requests":           self._network_requests,
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

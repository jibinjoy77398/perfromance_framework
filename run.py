"""
run.py — Single entry point for the Performance Testing Framework.

Usage:
    python run.py                           # all tests, all sites in config/sites.json
    python run.py --site "My App"           # one site by name
    python run.py --concurrent 10           # override baseline concurrency (default: 5)
    python run.py --ramp 1,2,5,10,20,50    # override breakpoint ramp steps
    python run.py --report-dir ./reports    # custom output directory
    python run.py --headful                 # show browser window
    python run.py --format json             # output JSON instead of HTML
    python run.py --tests baseline          # run only specific test module(s) (comma-separated)
                                            # options: load, resources, interactions, network,
                                            #          memory, baseline, stress, breakpoint, analysis
"""
from __future__ import annotations
import argparse
import asyncio
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Make sure project root is on the path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright
from pages.base_page import BasePage
from core.site_config import SiteConfig
from utils.threshold_evaluator import ThresholdEvaluator
from reporters.html_reporter import BaseReporter, HTMLReporter
from reporters.json_reporter import JSONReporter

CONFIG_PATH = ROOT / "config" / "sites.json"

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


# ══════════════════════════════════════════════════════════════════════════
#   PerformanceRunner — Encapsulates all test execution for a single site
# ══════════════════════════════════════════════════════════════════════════

class PerformanceRunner:
    """
    Encapsulates the full performance testing workflow for one site.

    OOP concepts demonstrated:
        - Encapsulation: all runner state (site, evaluator, reporter) is internal
        - Polymorphism: reporter can be HTMLReporter or JSONReporter

    Usage:
        site = SiteConfig(name="My App", url="https://myapp.com")
        runner = PerformanceRunner(site)
        await runner.run_all()
    """

    def __init__(
        self,
        site: SiteConfig,
        evaluator: ThresholdEvaluator | None = None,
        reporter: BaseReporter | None = None,
        headless: bool = True,
        concurrent: int = 5,
        ramp_steps: list[int] | None = None,
        report_dir: str = "reports",
    ):
        self._site = site
        self._evaluator = evaluator or ThresholdEvaluator()
        self._reporter = reporter or HTMLReporter()
        self._headless = headless
        self._concurrent = concurrent
        self._ramp_steps = ramp_steps or [1, 2, 5, 10, 20]
        self._report_dir = report_dir

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def site(self) -> SiteConfig:
        return self._site

    @property
    def reporter(self) -> BaseReporter:
        return self._reporter

    @reporter.setter
    def reporter(self, value: BaseReporter) -> None:
        """Swap reporter at runtime (polymorphism)."""
        self._reporter = value

    # ── Private helpers ──────────────────────────────────────────────────

    async def _collect_page_metrics(self, network_profile: str | None = None) -> dict:
        """Launch a browser, navigate, optionally login, collect metrics."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self._headless,
                args=["--disable-extensions", "--no-sandbox"],
            )
            ctx = await browser.new_context(ignore_https_errors=True)
            page = await ctx.new_page()
            if network_profile and network_profile in NETWORK_PROFILES:
                cdp = await ctx.new_cdp_session(page)
                await cdp.send("Network.enable")
                await cdp.send("Network.emulateNetworkConditions",
                               NETWORK_PROFILES[network_profile])
            bp = BasePage(page, self._site.url, login_url=self._site.login_url)
            await bp.setup()
            await bp.navigate()
            if self._site.has_credentials:
                await bp.login(
                    self._site.credentials.username,
                    self._site.credentials.password,
                )
                await bp.navigate()
            await bp.scroll_to_bottom()
            metrics = await bp.get_metrics()
            await browser.close()
            return metrics

    @staticmethod
    def _percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = int(len(s) * pct / 100)
        return s[min(idx, len(s) - 1)]

    # ── Test runners ─────────────────────────────────────────────────────

    async def run_core_metrics(self) -> tuple[dict, dict, str]:
        """Collect core metrics, evaluate, and grade."""
        print("  📊 Collecting core metrics …")
        metrics = await self._collect_page_metrics()
        evaluation = self._evaluator.evaluate(metrics)
        site_grade = self._evaluator.grade(evaluation)
        return metrics, evaluation, site_grade

    async def run_baseline(self, n: int | None = None) -> dict:
        """Run N concurrent sessions and return aggregated stats."""
        n = n or self._concurrent
        print(f"  ⚡ Baseline — {n} concurrent runs … ", end="", flush=True)
        tasks = [self._collect_page_metrics() for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, dict)]
        print(f"done ({len(valid)}/{n} ok)")
        if not valid:
            return {}

        vitals = ["fcp", "lcp", "ttfb", "cls", "tbt", "load_time", "dom_content_loaded"]
        stats = {}
        for v in vitals:
            vals = [r.get(v, 0) for r in valid]
            stats[v] = {
                "p50": round(self._percentile(vals, 50), 2),
                "p95": round(self._percentile(vals, 95), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "stddev": round(statistics.stdev(vals) if len(vals) > 1 else 0, 2),
                "runs": len(valid),
            }
        return stats

    async def run_network_stress(self) -> dict:
        """Test site under all network profiles."""
        results = {}
        for name in NETWORK_PROFILES:
            print(f"  📡 Network stress [{name}] … ", end="", flush=True)
            try:
                m = await self._collect_page_metrics(network_profile=name)
                results[name] = m
                print(f"LCP={m.get('lcp',0):.0f}ms  Load={m.get('load_time',0):.0f}ms")
            except Exception as e:
                print(f"ERROR: {e}")
                results[name] = {}
        return results

    async def run_breakpoint(self, steps: list[int] | None = None) -> list[dict]:
        """Ramp concurrent users to find the breakpoint."""
        steps = steps or self._ramp_steps
        thresholds = self._evaluator.thresholds
        all_levels = []
        for n in steps:
            print(f"  👥 Breakpoint ramp [{n} users] … ", end="", flush=True)
            sem = asyncio.Semaphore(n)

            async def _session(sem=sem):
                result = {"error": None, "load_time": 0, "ttfb": 0, "lcp": 0, "status": "ok"}
                async with sem:
                    try:
                        m = await self._collect_page_metrics()
                        result["load_time"] = m.get("load_time", 0)
                        result["ttfb"] = m.get("ttfb", 0)
                        result["lcp"] = m.get("lcp", 0)
                    except asyncio.TimeoutError:
                        result["status"] = "timeout"; result["error"] = "Timeout"
                    except Exception as e:
                        result["status"] = "exception"; result["error"] = str(e)
                return result

            results = await asyncio.gather(*[_session() for _ in range(n)])
            ok = [r for r in results if r["status"] == "ok"]
            failed = [r for r in results if r["status"] != "ok"]
            error_rate = (len(failed) / n) * 100
            load_times = sorted(r["load_time"] for r in ok) if ok else [0]
            p95_idx = int(len(load_times) * 0.95)
            p95 = load_times[min(p95_idx, len(load_times) - 1)]
            error_reasons: dict[str, int] = {}
            for r in failed:
                k = r.get("error", "unknown")
                error_reasons[k] = error_reasons.get(k, 0) + 1

            level = {
                "users": n,
                "ok": len(ok),
                "failed": len(failed),
                "error_rate_pct": round(error_rate, 1),
                "p95_load_time": round(p95, 1),
                "avg_ttfb": round(sum(r["ttfb"] for r in ok) / len(ok), 1) if ok else 0,
                "avg_lcp": round(sum(r["lcp"] for r in ok) / len(ok), 1) if ok else 0,
                "error_reasons": error_reasons,
            }
            all_levels.append(level)

            broke = error_rate > thresholds["error_rate_pct"] or p95 > thresholds["p95_load_time"]
            status = f"❌ BREAK (err={error_rate:.0f}% p95={p95:.0f}ms)" if broke else "✅"
            print(status)
            if broke:
                print(f"      Stopping ramp — breakpoint found at {n} users.")
                break
        return all_levels

    async def run_resource_analysis(self) -> tuple[dict, list]:
        """Collect and return resource breakdown."""
        print("  🔬 Resource analysis … ", end="", flush=True)
        metrics = await self._collect_page_metrics()
        groups = metrics.get("resources_by_type", {})
        requests = metrics.get("all_requests", [])
        print(f"{len(requests)} requests captured")
        return groups, requests

    # ── Full run ─────────────────────────────────────────────────────────

    async def run_all(self, enabled_tests: set[str] | None = None) -> None:
        """Run all enabled tests, evaluate, and generate report."""
        def should_run(key: str) -> bool:
            return enabled_tests is None or key in enabled_tests

        print(f"\n{'='*60}")
        print(f"  Site : {self._site.name}")
        print(f"  URL  : {self._site.url}")
        print(f"{'='*60}")

        t0 = time.monotonic()

        # Core metrics (always run)
        _, evaluation, site_grade = await self.run_core_metrics()

        # Baseline
        baseline_stats: dict = {}
        if should_run("baseline"):
            baseline_stats = await self.run_baseline()

        # Network stress
        network_results: dict = {}
        if should_run("stress"):
            network_results = await self.run_network_stress()

        # Breakpoint
        ramp_results: list = []
        if should_run("breakpoint"):
            ramp_results = await self.run_breakpoint()

        # Resource analysis
        resource_groups: dict = {}
        all_requests: list = []
        if should_run("analysis"):
            resource_groups, all_requests = await self.run_resource_analysis()

        duration = time.monotonic() - t0

        # Generate report via the configured reporter (polymorphism)
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_name = "".join(c if c.isalnum() else "_" for c in self._site.name)
        report_dir = Path(self._report_dir) / date_str
        report_path = report_dir / f"{safe_name}_report.html"

        self._reporter.generate(
            site_name=self._site.name,
            site_url=self._site.url,
            evaluation=evaluation,
            grade=site_grade,
            baseline_stats=baseline_stats,
            network_stress=network_results,
            ramp_results=ramp_results,
            resource_groups=resource_groups,
            all_requests=all_requests,
            output_path=report_path,
            duration_seconds=duration,
        )

        # Console summary
        passes = sum(1 for v in evaluation.values() if v["verdict"] == "PASS")
        warns  = sum(1 for v in evaluation.values() if v["verdict"] == "WARN")
        fails  = sum(1 for v in evaluation.values() if v["verdict"] == "FAIL")
        print(f"\n  Grade: {site_grade}  |  ✅ {passes} PASS  ⚠️  {warns} WARN  ❌ {fails} FAIL")
        print(f"  Duration: {duration:.1f}s")


# ══════════════════════════════════════════════════════════════════════════
#   CLI — Entry point
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Python Playwright POM Performance Testing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--site", default=None,
                        help="Run only the named site from sites.json")
    parser.add_argument("--concurrent", type=int, default=5,
                        help="Number of concurrent sessions for baseline test (default: 5)")
    parser.add_argument("--ramp", default="1,2,5,10,20",
                        help="Comma-separated ramp steps for breakpoint finder")
    parser.add_argument("--report-dir", default="reports",
                        help="Directory to save reports (default: ./reports)")
    parser.add_argument("--headful", action="store_true",
                        help="Show browser window during testing")
    parser.add_argument("--format", choices=["html", "json"], default="html",
                        help="Output report format: html (default) or json")
    parser.add_argument("--tests", default=None,
                        help="Comma-separated test modules to run: "
                             "load,resources,interactions,network,memory,"
                             "baseline,stress,breakpoint,analysis")
    # Locator Discovery flags
    parser.add_argument("--discover", action="store_true",
                        help="Scan sites for locators and cache results")
    parser.add_argument("--serve", action="store_true",
                        help="Start the Locator Discovery API server")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port for the API server (default: 8000)")
    args = parser.parse_args()

    # ── Mode: Serve API ──────────────────────────────────────────────────
    if args.serve:
        import uvicorn
        print(f"\n🌐  Starting Locator Discovery API on port {args.port}\n")
        uvicorn.run("api.server:app", host="0.0.0.0", port=args.port, reload=False)
        return

    # ── Mode: Discover locators ──────────────────────────────────────────
    if args.discover:
        from locator_service.scanner import PageScanner
        from locator_service.locator_generator import LocatorGenerator
        from locator_service.cache import LocatorCache
        from locator_service.models import ScanResponse
        from locator_service.browser_pool import BrowserPool

        sites = SiteConfig.load_all(CONFIG_PATH)
        if args.site:
            sites = [s for s in sites if s.name == args.site]
            if not sites:
                print(f"ERROR: No site named '{args.site}' in {CONFIG_PATH}")
                sys.exit(1)

        async def discover_all():
            pool = BrowserPool.instance()
            await pool.start()
            cache = LocatorCache()
            await cache.init()
            scanner = PageScanner(pool)
            generator = LocatorGenerator()

            for site in sites:
                target = site.login_url or site.url
                print(f"\n  🔍 Discovering locators: {site.name} → {target}")
                try:
                    raw_elements, aria_tree = await scanner.scan(target)
                    locators = generator.generate_all(raw_elements, aria_tree)
                    response = ScanResponse(
                        url=target,
                        source="fresh",
                        element_count=len(locators),
                        elements=locators,
                    )
                    await cache.set(target, response)
                    print(f"    ✅ {len(locators)} elements found and cached")
                except Exception as e:
                    print(f"    ❌ Error: {e}")

            await pool.stop()

        asyncio.run(discover_all())
        print("\n✅  Discovery complete.\n")
        return

    # ── Mode: Performance tests (default) ────────────────────────────────
    # Export env vars consumed by test files
    os.environ["PERF_CONCURRENT"] = str(args.concurrent)
    os.environ["PERF_RAMP_STEPS"] = args.ramp

    # Load sites
    sites = SiteConfig.load_all(CONFIG_PATH)
    if args.site:
        sites = [s for s in sites if s.name == args.site]
        if not sites:
            print(f"ERROR: No site named '{args.site}' in {CONFIG_PATH}")
            sys.exit(1)

    # Select reporter (polymorphism)
    reporter: BaseReporter = JSONReporter() if args.format == "json" else HTMLReporter()

    # Shared evaluator
    evaluator = ThresholdEvaluator()

    # Parse options
    ramp_steps = [int(x) for x in args.ramp.split(",")]
    headless = not args.headful
    enabled = set(args.tests.lower().split(",")) if args.tests else None

    print("\n🚀  Performance Framework — Starting\n")
    print(f"   Sites     : {len(sites)}")
    print(f"   Concurrent: {args.concurrent}")
    print(f"   Ramp steps: {args.ramp}")
    print(f"   Format    : {args.format}")
    print(f"   Reports   : {args.report_dir}/")

    async def run_all():
        for site in sites:
            runner = PerformanceRunner(
                site=site,
                evaluator=evaluator,
                reporter=reporter,
                headless=headless,
                concurrent=args.concurrent,
                ramp_steps=ramp_steps,
                report_dir=args.report_dir,
            )
            await runner.run_all(enabled_tests=enabled)

    asyncio.run(run_all())
    print("\n✅  All done.\n")


if __name__ == "__main__":
    main()

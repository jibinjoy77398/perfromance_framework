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
from helpers.threshold_evaluator import ThresholdEvaluator
from reporters.html_reporter import BaseReporter, HTMLReporter
from reporters.json_reporter import JSONReporter

CONFIG_PATH = ROOT / "config" / "sites.json"

from core.runner import PerformanceRunner


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
    parser.add_argument("--spike", type=int, default=0,
                        help="Run a Hybrid HTTP DDOS spike of N requests simultaneously.")
    parser.add_argument("--soak", type=float, default=0,
                        help="Run in Endurance Mode, continuously looping tests for X hours.")
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
        print(f"\n🌐 Starting Unified Performance & Discovery Hub on port {args.port}")
        print(f"   🏠 View Dashboard: http://localhost:{args.port}/")
        print(f"   ⚡ APIs enabled    : /run-perf, /scan, /health\n")
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

    async def run_all_sites():
        if args.soak > 0:
            print(f"\n🌊 SOAK TEST INITIATED: {args.soak} hours.")
            end_time = time.monotonic() + (args.soak * 3600)
            iteration = 0
            while time.monotonic() < end_time:
                iteration += 1
                rem = (end_time - time.monotonic()) / 3600
                print(f"\n--- 🌊 Soak Iteration {iteration} | Time Remaining: {rem:.2f}h ---")
                
                generated = []
                for site in sites:
                    runner = PerformanceRunner(
                        site=site, evaluator=evaluator, reporter=reporter, headless=headless,
                        concurrent=args.concurrent, ramp_steps=ramp_steps, report_dir=args.report_dir
                    )
                    res = await runner.run_all(enabled_tests=enabled, spike_requests=args.spike)
                    path = res[0] if isinstance(res, tuple) else res
                    generated.append((site.name, path))
                
                print(f"--- Iteration {iteration} complete. Sleeping 60s to flush memory buffers. ---")
                await asyncio.sleep(60)
            print("\n🌊 SOAK TEST COMPLETE.")
            return

        generated = []
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
            res = await runner.run_all(enabled_tests=enabled, spike_requests=args.spike)
            path = res[0] if isinstance(res, tuple) else res
            generated.append((site.name, path))
            
        # Create a root index.html for live GitHub Pages deployment natively
        if generated and args.format == "html":
            idx = Path(args.report_dir) / "index.html"
            links = "".join(f'<li><a href="{(p[0] if isinstance(p, tuple) else p).relative_to(args.report_dir).as_posix()}" style="color:#818CF8;font-size:1.2rem;text-decoration:none;">📊 View {n} Report</a></li>' for n, p in generated)
            html = f'''<!DOCTYPE html><html><body style="background:#0B1120;color:#F8FAFC;font-family:sans-serif;padding:3rem;">
            <h1 style="margin-bottom:2rem;">Performance Framework Hub</h1><ul>{links}</ul></body></html>'''
            idx.write_text(html, encoding="utf-8")

    asyncio.run(run_all_sites())
    print("\n✅  All done.\n")


if __name__ == "__main__":
    main()

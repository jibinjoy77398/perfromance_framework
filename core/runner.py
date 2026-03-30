"""
runner.py — Encapsulates the execution engine for the Performance Framework.
"""
from __future__ import annotations
import asyncio
import statistics
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from pages.base_page import BasePage
from core.site_config import SiteConfig
from helpers.threshold_evaluator import ThresholdEvaluator
from reporters.html_reporter import BaseReporter, HTMLReporter
from utils.lighthouse_comparator import LighthouseComparator

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

class PerformanceRunner:
    """
    Encapsulates the full performance testing workflow for one site.
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
        self._ramp_steps = ramp_steps or [5, 10, 20, 35, 50]
        self._report_dir = report_dir
        self._browser = None

    @property
    def site(self) -> SiteConfig:
        return self._site

    @property
    def reporter(self) -> BaseReporter:
        return self._reporter

    @reporter.setter
    def reporter(self, value: BaseReporter) -> None:
        self._reporter = value

    def _safe_float(self, value, default=0.0):
        try:
            if value is None or value == '' or value == 'null' or value == 'N/A':
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    async def _collect_page_metrics(self, network_profile: str | None = None, anonymous: bool = False, force_fast_3g: bool = False) -> tuple[dict, float]:
        # FIX: Bug 4 - All asset sizes and avg ms show 0.0 KB / 0 ms corrected so changes are traceable
        import json
        har_path = Path("reports") / f"trace_{int(time.time())}_{id(asyncio.current_task())}.har"
        ctx = await self._browser.new_context(ignore_https_errors=True, record_har_path=str(har_path))
        page = await ctx.new_page()
        
        # Resource Monitoring & Throttling
        bp = BasePage(page, self._site.url, login_url=self._site.login_url)
        await bp.setup()
        
        if force_fast_3g:
            # CDPSession isolation: Throttling established for this specific context
            await bp._collector.apply_fast_3g_throttling()
        elif network_profile and network_profile in NETWORK_PROFILES:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Network.emulateNetworkConditions", NETWORK_PROFILES[network_profile])
            
        await bp.navigate()
        auth_speed = 0.0
        if self._site.has_credentials and not anonymous:
            auth_speed = await bp.login(
                self._site.credentials.username,
                self._site.credentials.password,
            )
            await bp.navigate()
            
        if self._site.journey:
            await bp.run_journey(self._site.journey)
            
        await bp.scroll_to_bottom()
        metrics = await bp.get_metrics()
        await ctx.close() # Flushes HAR

        # Parse HAR for accurate sizes and durations
        if har_path.exists():
            try:
                with open(har_path, "r", encoding="utf-8") as f:
                    har_data = json.load(f)
                
                # Update metrics with HAR data
                har_requests = []
                for entry in har_data.get("log", {}).get("entries", []):
                    req = entry.get("request", {})
                    resp = entry.get("response", {})
                    timings = entry.get("timings", {})
                    res_type = entry.get("_resourceType", "other")
                    size = resp.get("content", {}).get("size", 0)
                    duration = timings.get("receive", 0)
                    if duration < 0: duration = 0
                    har_requests.append({
                        "url": req.get("url"), "resource_type": res_type,
                        "size": size, "duration": duration, "status": resp.get("status"),
                    })
                
                if "all_requests" in metrics:
                    metrics["all_requests"] = har_requests
                    metrics["resource_count"] = len(har_requests)
                    metrics["total_resource_size_kb"] = round(sum(r["size"] for r in har_requests) / 1024, 2)
                    grouped = {}
                    for r in har_requests:
                        t = r["resource_type"] or "other"
                        if t not in grouped: grouped[t] = {"count": 0, "total_size_kb": 0, "requests": []}
                        grouped[t]["count"] += 1
                        grouped[t]["total_size_kb"] += r["size"] / 1024
                        grouped[t]["requests"].append(r)
                    for t in grouped: grouped[t]["total_size_kb"] = round(grouped[t]["total_size_kb"], 2)
                    metrics["resources_by_type"] = grouped
                har_path.unlink()
            except Exception: pass
                
        return metrics, auth_speed

    def _percentile(self, data, pct):
        data = [self._safe_float(x) for x in data if x is not None]
        if not data:
            return 0.0
        data = sorted(data)
        index = (pct / 100) * (len(data) - 1)
        lower = int(index)
        upper = min(lower + 1, len(data) - 1)
        fraction = index - lower
        return data[lower] + (data[upper] - data[lower]) * fraction

    async def run_core_metrics(self, anonymous: bool = False) -> tuple[dict, dict, str, float, dict | None]:
        print("  📊 Collecting core metrics …")
        metrics, auth_speed = await self._collect_page_metrics(anonymous=anonymous)
        evaluation = self._evaluator.evaluate(metrics)
        site_grade = self._evaluator.grade(evaluation)
        
        # NEW: improvement 2 — Lighthouse Comparison
        lh_comp = None
        if LighthouseComparator.is_available():
            lh_res = await LighthouseComparator.run_audit(self._site.url)
            if lh_res and lh_res.get("available") and "metrics" in lh_res:
                lh_comp = LighthouseComparator.compare(metrics, lh_res["metrics"])
        
        return metrics, evaluation, site_grade, auth_speed, lh_comp

    async def run_baseline(self, n: int | None = None, anonymous: bool = False) -> dict:
        n = n or self._concurrent
        print(f"  ⚡ Baseline — {n} concurrent runs … ", end="", flush=True)
        tasks = [self._collect_page_metrics(anonymous=anonymous) for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r[0] for r in results if isinstance(r, tuple)]
        print(f"done ({len(valid)}/{n} ok)")
        if not valid:
            return {}

        vitals = ["fcp", "lcp", "ttfb", "cls", "tbt", "load_time", "dom_content_loaded"]
        stats = {}
        for v in vitals:
            vals = [self._safe_float(r.get(v)) for r in valid]
            if not vals:
                stats[v] = { "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "stddev": 0.0, "runs": 0 }
                continue

            stats[v] = {
                "p50": round(self._safe_float(self._percentile(vals, 50)), 2),
                "p95": round(self._safe_float(self._percentile(vals, 95)), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "stddev": round(statistics.stdev(vals) if len(vals) > 1 else 0, 2),
                "runs": len(valid),
            }
        return stats

    async def run_network_stress(self, anonymous: bool = False) -> dict:
        results = {}
        for name in NETWORK_PROFILES:
            print(f"  📡 Network stress [{name}] … ", end="", flush=True)
            try:
                m, _ = await self._collect_page_metrics(network_profile=name, anonymous=anonymous)
                results[name] = m
                lcp = self._safe_float(m.get('lcp'))
                load = self._safe_float(m.get('load_time'))
                print(f"LCP={lcp:.0f}ms  Load={load:.0f}ms")
            except Exception as e:
                print(f"ERROR: {e}")
                results[name] = {}
        return results

    async def run_breakpoint(self, steps: list[int] | None = None, anonymous: bool = False) -> list[dict]:
        steps = steps or self._ramp_steps
        thresholds = self._evaluator.thresholds
        all_levels = []
        for n in steps:
            print(f"  👥 {'Concurrent Login Protocol' if not anonymous else 'Anonymous Capacity'} [{n} users] … ", end="", flush=True)
            sem = asyncio.Semaphore(n)

            async def _session(sem=sem):
                result = {"error": None, "load_time": 0, "ttfb": 0, "lcp": 0, "status": "ok"}
                async with sem:
                    try:
                        m, _ = await self._collect_page_metrics(anonymous=anonymous)
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
            load_times = sorted(self._safe_float(r["load_time"]) for r in ok) if ok else [0.0]
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
                "error_rate_pct": round(self._safe_float(error_rate), 1),
                "p95_load_time": round(self._safe_float(p95), 1),
                "avg_ttfb": round(sum(self._safe_float(r["ttfb"]) for r in ok) / len(ok), 1) if ok else 0,
                "avg_lcp": round(sum(self._safe_float(r["lcp"]) for r in ok) / len(ok), 1) if ok else 0,
                "error_reasons": error_reasons,
            }
            all_levels.append(level)

            broke = error_rate > self._safe_float(thresholds["error_rate_pct"]) or self._safe_float(p95) > self._safe_float(thresholds["p95_load_time"])
            status = f"❌ BREAK (err={self._safe_float(error_rate):.0f}% p95={self._safe_float(p95):.0f}ms)" if broke else "✅"
            print(status)
            if broke:
                print(f"      Stopping ramp — breakpoint found at {n} users.")
                break
        return all_levels

    async def run_crash_test(self, user_counts: list[int] = [5, 10, 20], anonymous: bool = False) -> dict:
        """
        Executes a 'Crash Test': Concurrent Load Test with bandwidth isolation and median stats.
        """
        print(f"\n  🔥 CRASH TEST — Starting Concurrent Load Sequence…")
        crash_results = {}
        
        for n in user_counts:
            print(f"    👥 Testing {n} Concurrent Users (Fast 3G Isolation) … ", end="", flush=True)
            tasks = [self._collect_page_metrics(anonymous=anonymous, force_fast_3g=True) for _ in range(n)]
            
            # Context Isolation + asyncio.gather concurrency
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            valid = [o[0] for o in outcomes if isinstance(o, tuple) and isinstance(o[0], dict)]
            
            if not valid:
                print(f"Failed (0/{n} succeeded)")
                crash_results[n] = "failed"
                continue
                
            # Averaging Logic: Median for FCP/LCP
            fcp_vals = sorted(v.get("fcp", 0) for v in valid if isinstance(v.get("fcp"), (int, float)))
            lcp_vals = sorted(v.get("lcp", 0) for v in valid if isinstance(v.get("lcp"), (int, float)))
            
            def get_median(sorted_data):
                if not sorted_data: return 0
                middle = len(sorted_data) // 2
                return sorted_data[middle] if len(sorted_data) % 2 != 0 else (sorted_data[middle-1] + sorted_data[middle]) / 2

            median_fcp = get_median(fcp_vals)
            median_lcp = get_median(lcp_vals)
            
            # Resource Monitoring
            avg_heap = sum(v.get("js_heap_used_mb", 0) for v in valid) / len(valid)
            avg_res_count = sum(v.get("resource_count", 0) for v in valid) / len(valid)

            crash_results[n] = {
                "median_fcp": round(self._safe_float(median_fcp), 1),
                "median_lcp": round(self._safe_float(median_lcp), 1),
                "avg_js_heap_mb": round(self._safe_float(avg_heap), 1),
                "avg_resource_count": int(self._safe_float(avg_res_count)),
                "success_rate": f"{len(valid)}/{n}"
            }
            print(f"done | Median LCP: {median_lcp:.0f}ms | Avg Heap: {avg_heap:.1f}MB")

        # Visual Console Output for Plotting
        print(f"\n  📊 RESPONSE TIME VS USER COUNT (CRASH TEST RESULTS)")
        print(f"  {'Users':<8} | {'Median LCP (ms)':<15} | {'Heap (MB)':<10} | {'Success'}")
        print(f"  {'-'*45}")
        for n, data in crash_results.items():
            if isinstance(data, dict):
                print(f"  {n:<8} | {data['median_lcp']:<15.0f} | {data['avg_js_heap_mb']:<10.1f} | {data['success_rate']}")
        
        return crash_results

    async def run_resource_analysis(self, anonymous: bool = True) -> tuple[dict, list]:
        """Analyse page resources and return resource group and request list."""
        ctx = await self._browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        try:
            requests = []
            page.on("request", lambda req: requests.append(req))
            await page.goto(self._site.url, wait_until="networkidle", timeout=30000)
            resource_group = await page.evaluate("""() => {
                const resources = performance.getEntriesByType('resource');
                const groups = {};
                resources.forEach(r => {
                    const type = r.initiatorType || 'other';
                    if (!groups[type]) {
                        groups[type] = {
                            count: 0,
                            total_size_kb: 0,
                            avg_duration_ms: 0,
                            _total_duration: 0
                        };
                    }
                    groups[type].count += 1;
                    groups[type].total_size_kb += (r.transferSize || 0) / 1024;
                    groups[type]._total_duration += r.duration || 0;
                    groups[type].avg_duration_ms = groups[type]._total_duration / groups[type].count;
                });
                // Remove internal accumulator before returning
                Object.values(groups).forEach(g => delete g._total_duration);
                return groups;
            }""")
            return resource_group, requests
        finally:
            await page.close()
            await ctx.close()
        import aiohttp
        print(f"  🌪️  Hybrid Spike [{requests} instantaneous HTTP requests] … ", end="", flush=True)
        results = {"success": 0, "failed": 0, "avg_time": 0}
        
        async def fetch(session, url):
            t = time.monotonic()
            try:
                async with session.get(url, ssl=False, timeout=30) as resp:
                    await resp.read()
                    return True, time.monotonic() - t
            except Exception:
                return False, 0
                
        async with aiohttp.ClientSession() as session:
            tasks = [fetch(session, self._site.url) for _ in range(requests)]
            ui_task = self._collect_page_metrics(anonymous=anonymous)
            
            # Execute HTTP spike precisely while Playwright renders the UI
            outcomes = await asyncio.gather(*tasks, ui_task, return_exceptions=True)
        
        ui_res = outcomes.pop()
        for r in outcomes:
            if isinstance(r, tuple) and r[0]:
                results["success"] += 1
                results["avg_time"] += r[1]
            else:
                results["failed"] += 1
                
        if results["success"] > 0:
            results["avg_time"] = round(self._safe_float(results["avg_time"] / results["success"]) * 1000, 1)
            
        ui_latency = "ERROR"
        if isinstance(ui_res, tuple) and isinstance(ui_res[0], dict):
            ui_latency = round(self._safe_float(ui_res[0].get("load_time", 0)))
            
        print(f"done ({results['success']} OK, {results['failed']} ERR) | UI Time under spike: {ui_latency}ms")
        return results

    async def run_scalability(self, plateau_minutes: int = 5, anonymous: bool = False) -> dict:
        """
        Executes a Scalability Stress test: 
        1. Ramp up to Max (already handled by run_breakpoint logic)
        2. Hold Plateau for N minutes
        3. Sudden scale-down to 0.
        """
        print(f"  📈 Scalability Plateau [Holding {self._ramp_steps[-1]} users for {plateau_minutes}m] … ", end="", flush=True)
        # We simulate the plateau by periodically sampling metrics during the hold period
        samples = []
        end_plateau = time.monotonic() + (plateau_minutes * 60)
        while time.monotonic() < end_plateau:
            res, _, _, _ = await self.run_core_metrics(anonymous=anonymous)
            samples.append(self._safe_float(res.get("ttfb", 0)))
            await asyncio.sleep(60) # Sample every minute
            
        avg_plateau_ttfb = round(self._safe_float(statistics.mean(samples)), 1) if samples else 0
        print(f"done (Avg Plateau TTFB: {avg_plateau_ttfb}ms)")
        return {"avg_plateau_ttfb": avg_plateau_ttfb, "samples": samples}

    async def run_all(
        self, 
        enabled_tests: set[str] | None = None, 
        spike_requests: int = 0,
        soak_hours: float = 0,
        scalability_plateau: int = 0
    ) -> Path:
        def should_run(key: str) -> bool:
            return enabled_tests is None or key in enabled_tests

        print(f"\n{'='*60}")
        print(f"  Site : {self._site.name}")
        print(f"  URL  : {self._site.url}")
        print(f"{'='*60}")

        t0 = time.monotonic()
        modes = ["anonymous", "authenticated"] if self._site.has_credentials else ["anonymous"]
        final_results = {}

        for mode in modes:
            async with async_playwright() as p:
                self._browser = await p.chromium.launch(
                    headless=self._headless,
                    args=[
                        "--disable-extensions", 
                        "--no-sandbox",
                        "--disable-dev-shm-usage",           # Prevents restricted memory segment crashes
                        "--js-flags=--max-old-space-size=8192", # Assign 8GB of RAM to V8 Engine
                        "--disk-cache-size=1073741824"       # Allocate 1GB to local disk cache
                    ],
                )
                try:
                    anon = (mode == "anonymous")
                    if len(modes) > 1:
                        print(f"\n  [{modes.index(mode)+1}/{len(modes)}] {'🕵️ Anonymous (Public Traffic)' if anon else '🔐 Authenticated (Private Traffic)'}")
                        
                    # 1. Run Baseline (Provides P95 and core stats directly)
                    # Updated to include Lighthouse Comparison results if available
                    metrics, eval_res, grade, auth_speed, lh_comp = await self.run_core_metrics(anonymous=anon)
                    
                    # Extract representative core metrics from baseline for grading
                    # baseline_stats = await self.run_baseline(anonymous=anon)
                    # wait, baseline_stats is already called below. 
                    # Let's keep it simple and just use the first core metrics run for Lighthouse.
                    
                    # 2. Network/Stress Tests
                    spike_res = None
                    if spike_requests > 0 and should_run("spike"):
                        spike_res = await self.run_spike(spike_requests, anonymous=anon)
                    
                    scalability_res = None
                    if scalability_plateau > 0 and should_run("scalability"):
                        scalability_res = await self.run_scalability(scalability_plateau, anonymous=anon)
                        
                    b_stats = await self.run_baseline(anonymous=anon) if should_run("baseline") else {}
                    n_stats = await self.run_network_stress(anonymous=anon) if should_run("stress") else {}
                    r_stats = await self.run_breakpoint(anonymous=anon) if should_run("breakpoint") else []
                    rg_raw, reqs = await self.run_resource_analysis(anonymous=anon) if should_run("analysis") else ({}, [])
                    rg = rg_raw if rg_raw else {}

                    final_results[mode] = {
                        "evaluation": eval_res,
                        "grade": grade,
                        "auth_speed": auth_speed,
                        "baseline_stats": b_stats,
                        "network_stress": n_stats,
                        "ramp_results": r_stats,
                        "spike_results": spike_res,
                        "scalability_results": scalability_res,
                        "resource_groups": rg,
                        "all_requests": reqs,
                        "lighthouse_comparison": lh_comp # NEW: improvement 2
                    }

                except Exception as e:
                    print(f"  [CRITICAL] Error in mode '{mode}': {e}")
                    # Add empty fallback to allow reporter loop to continue
                    final_results[mode] = {
                        "evaluation": {}, "grade": "F", "auth_speed": 0.0,
                        "baseline_stats": {}, "network_stress": {}, "ramp_results": [],
                        "spike_results": None, "scalability_results": None, "resource_groups": {}, "all_requests": []
                    }
                finally:
                    if self._browser:
                        await self._browser.close()
                        self._browser = None

        # Post-process: Generate report
        duration = time.monotonic() - t0
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_name = f"{self._site.name.replace(' ', '_').lower()}_report.html"
        report_dir = Path(self._report_dir) / date_str
        report_path = report_dir / report_name
        
        # Ensure report directory exists
        report_dir.mkdir(parents=True, exist_ok=True)
        
        rel_url = f"/reports/{date_str}/{report_name}"
        
        self._reporter.generate(
            site_name=self._site.name,
            site_url=self._site.url,
            results=final_results,
            output_path=report_path,
            duration_seconds=duration
        )

        try:
            # Use the first available mode for the main grade/stats
            main_mode = "authenticated" if "authenticated" in final_results else "anonymous"
            main_data = final_results.get(main_mode, {})
            ev = main_data.get("evaluation", {})
            passes = sum(1 for v in ev.values() if v.get("verdict") == "PASS")
            fails  = sum(1 for v in ev.values() if v.get("verdict") == "FAIL")

            from helpers.db_service import DBService
            DBService.log_report(
                name=f"{self._site.name} Performance Audit",
                site=self._site.url,
                date=date_str,
                url=rel_url,
                grade=main_data.get("grade", "F"),
                passed=passes,
                failed=fails,
                duration=round(self._safe_float(duration), 2)
            )
        except Exception as db_err:
            print(f"  [WARN] Failed to log report to database: {db_err}")

        for mode, data in final_results.items():
            ev = data.get("evaluation", {})
            passes = sum(1 for v in ev.values() if v.get("verdict") == "PASS")
            warns  = sum(1 for v in ev.values() if v.get("verdict") == "WARN")
            fails  = sum(1 for v in ev.values() if v.get("verdict") == "FAIL")
            print(f"  [{mode.upper()}] Grade: {data.get('grade','F')}  |  ✅ {passes} PASS  ⚠️  {warns} WARN  ❌ {fails} FAIL")
        print(f"  Total Duration: {float(self._safe_float(duration)):.1f}s")
        return report_path, final_results

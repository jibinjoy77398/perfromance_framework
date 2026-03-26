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
from utils.threshold_evaluator import ThresholdEvaluator
from reporters.html_reporter import BaseReporter, HTMLReporter

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

    async def _collect_page_metrics(self, network_profile: str | None = None, anonymous: bool = False) -> tuple[dict, float]:
        ctx = await self._browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        if network_profile and network_profile in NETWORK_PROFILES:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Network.emulateNetworkConditions",
                           NETWORK_PROFILES[network_profile])
        bp = BasePage(page, self._site.url, login_url=self._site.login_url)
        await bp.setup()
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
        await ctx.close()
        return metrics, auth_speed

    @staticmethod
    def _percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = int(len(s) * pct / 100)
        return s[min(idx, len(s) - 1)]

    async def run_core_metrics(self, anonymous: bool = False) -> tuple[dict, dict, str, float]:
        print("  📊 Collecting core metrics …")
        metrics, auth_speed = await self._collect_page_metrics(anonymous=anonymous)
        evaluation = self._evaluator.evaluate(metrics)
        site_grade = self._evaluator.grade(evaluation)
        return metrics, evaluation, site_grade, auth_speed

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

    async def run_network_stress(self, anonymous: bool = False) -> dict:
        results = {}
        for name in NETWORK_PROFILES:
            print(f"  📡 Network stress [{name}] … ", end="", flush=True)
            try:
                m, _ = await self._collect_page_metrics(network_profile=name, anonymous=anonymous)
                results[name] = m
                print(f"LCP={m.get('lcp',0):.0f}ms  Load={m.get('load_time',0):.0f}ms")
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

    async def run_resource_analysis(self, anonymous: bool = False) -> tuple[dict, list]:
        print("  🔬 Resource analysis … ", end="", flush=True)
        metrics, _ = await self._collect_page_metrics(anonymous=anonymous)
        groups = metrics.get("resources_by_type", {})
        requests = metrics.get("all_requests", [])
        print(f"{len(requests)} requests captured")
        return groups, requests

    async def run_spike(self, requests: int, anonymous: bool = False) -> dict:
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
            results["avg_time"] = round((results["avg_time"] / results["success"]) * 1000, 1)
            
        ui_latency = "ERROR"
        if isinstance(ui_res, tuple) and isinstance(ui_res[0], dict):
            ui_latency = round(ui_res[0].get("load_time", 0))
            
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
            samples.append(res.get("ttfb", 0))
            await asyncio.sleep(60) # Sample every minute
            
        avg_plateau_ttfb = round(statistics.mean(samples), 1) if samples else 0
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
                for mode in modes:
                    anon = (mode == "anonymous")
                    if len(modes) > 1:
                        print(f"\n  [{modes.index(mode)+1}/{len(modes)}] {'🕵️ Anonymous (Public Traffic)' if anon else '🔐 Authenticated (Private Traffic)'}")
                        
                    _, eval_res, grade, auth_speed = await self.run_core_metrics(anonymous=anon)
                    
                    if spike_requests > 0 and should_run("spike"):
                        await self.run_spike(spike_requests, anonymous=anon)
                    
                    if scalability_plateau > 0 and should_run("scalability"):
                        await self.run_scalability(scalability_plateau, anonymous=anon)
                        
                    b_stats = await self.run_baseline(anonymous=anon) if should_run("baseline") else {}
                    n_stats = await self.run_network_stress(anonymous=anon) if should_run("stress") else {}
                    r_stats = await self.run_breakpoint(anonymous=anon) if should_run("breakpoint") else []
                    rg, reqs = await self.run_resource_analysis(anonymous=anon) if should_run("analysis") else ({}, [])

                    final_results[mode] = {
                        "evaluation": eval_res,
                        "grade": grade,
                        "auth_speed": auth_speed,
                        "baseline_stats": b_stats,
                        "network_stress": n_stats,
                        "ramp_results": r_stats,
                        "resource_groups": rg,
                        "all_requests": reqs
                    }

                duration = time.monotonic() - t0

                date_str = datetime.now().strftime("%Y-%m-%d")
                safe_name = "".join(c if c.isalnum() else "_" for c in self._site.name)
                report_dir = Path(self._report_dir) / date_str
                report_path = report_dir / f"{safe_name}_report.html"

                self._reporter.generate(
                    site_name=self._site.name,
                    site_url=self._site.url,
                    results=final_results,
                    output_path=report_path,
                    duration_seconds=duration,
                )

                # Log to SQLite Database for History tab reliability
                try:
                    from utils.db_service import DBService
                    # Use the first available mode for the main grade/stats
                    main_mode = "authenticated" if "authenticated" in final_results else "anonymous"
                    main_data = final_results[main_mode]
                    ev = main_data["evaluation"]
                    passes = sum(1 for v in ev.values() if v["verdict"] == "PASS")
                    fails  = sum(1 for v in ev.values() if v["verdict"] == "FAIL")
                    
                    # Convert absolute path to relative for the web server
                    rel_url = f"/reports/{report_path.parent.name}/{report_path.name}"
                    
                    DBService.log_report(
                        name=f"{self._site.name} Performance Audit",
                        site=self._site.url,
                        date=date_str,
                        url=rel_url,
                        grade=main_data["grade"],
                        passed=passes,
                        failed=fails,
                        duration=round(duration, 2)
                    )
                except Exception as db_err:
                    print(f"  [WARN] Failed to log report to database: {db_err}")

                for mode, data in final_results.items():
                    ev = data["evaluation"]
                    passes = sum(1 for v in ev.values() if v["verdict"] == "PASS")
                    warns  = sum(1 for v in ev.values() if v["verdict"] == "WARN")
                    fails  = sum(1 for v in ev.values() if v["verdict"] == "FAIL")
                    print(f"  [{mode.upper()}] Grade: {data['grade']}  |  ✅ {passes} PASS  ⚠️  {warns} WARN  ❌ {fails} FAIL")
                print(f"  Total Duration: {duration:.1f}s")
                return report_path
            finally:
                if self._browser:
                    await self._browser.close()
                    self._browser = None

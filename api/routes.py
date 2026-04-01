from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import json
import uuid
from pathlib import Path

from core.runner import PerformanceRunner
from core.site_config import SiteConfig, Credentials
from helpers.email_service import EmailService

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from locator_service.browser_pool import BrowserPool
from locator_service.cache import LocatorCache
from locator_service.scanner import PageScanner, ScanError
from locator_service.locator_generator import LocatorGenerator
from locator_service.models import ScanResponse

_generator = LocatorGenerator()
_cache = LocatorCache()
_scanner = PageScanner()

# NEW: progress bar state store
progress_store: Dict[str, Dict] = {}

router = APIRouter()

# Dynamic path resolution for Docker/Cross-platform compatibility
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


@router.get("/scan", response_model=ScanResponse)
async def scan_url(
    url: str = Query(..., description="URL to scan for locators"),
    force_refresh: bool = Query(False, description="Skip cache and re-scan"),
    include_hidden: bool = Query(False, description="Include hidden elements"),
):
    """
    Scan a webpage and return locators for all interactive elements.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    if not force_refresh:
        cached = await _cache.get(url)
        if cached:
            return cached

    try:
        raw_elements, aria_tree = await _scanner.scan(url, include_hidden=include_hidden)
    except ScanError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    locators = _generator.generate_all(raw_elements, aria_tree)
    response = ScanResponse(
        url=url,
        source="fresh",
        scanned_at=datetime.now().isoformat(),
        element_count=len(locators),
        elements=locators,
    )
    await _cache.set(url, response)
    return response


from helpers.db_service import DBService

@router.get("/api/reports")
async def list_reports():
    """Lists all generated HTML reports from the database."""
    return DBService.get_all_reports()


@router.get("/api/metrics")
async def get_metrics():
    """Returns the latest performance metrics JSON."""
    metrics_file = PROJECT_ROOT / "latest_results.json"
    if metrics_file.exists():
        return json.loads(metrics_file.read_text())
    return {"status": "waiting"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    pool = BrowserPool.instance()
    return {
        "status": "healthy",
        "browser_running": pool.is_running,
        "timestamp": datetime.now().isoformat(),
    }

# NEW: progress bar endpoint
@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Returns the current progress for a given task ID."""
    if task_id not in progress_store:
        raise HTTPException(status_code=404, detail="Task ID not found")
    return progress_store[task_id]


class PerfRequest(BaseModel):
    url: str
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    journey: Optional[List[Dict]] = None
    
    test_type: str = "standard"
    interaction_count: int = 1
    spike_requests: int = 0
    scalability_plateau: int = 0
    email_notification: Optional[str] = None
    dos: bool = False


async def _background_perf_task(req: PerfRequest, report_id: str, task_id: str):
    """
    Background worker that runs the test, generates the report, 
    and sends email notifications.
    """
    # NEW: progress bar - Initial State
    progress_store[task_id] = {
        "status": "running", "percent": 5, "stage": "Starting browser...",
        "device": "desktop", "error": None
    }
    
    try:
        # 15% - Collecting metrics (desktop-only logic currently)
        progress_store[task_id].update({"percent": 15, "stage": "Collecting core metrics (desktop)..."})
        
        site = SiteConfig(
            name=req.url.split("//")[-1].split("/")[0],
            url=req.url,
            login_url=req.login_url or req.url,
            journey=req.journey
        )
        if req.username and req.password:
            site.credentials = Credentials(username=req.username, password=req.password)
            
        runner = PerformanceRunner(site=site, headless=True, report_dir=str(REPORTS_DIR))
        
        # Determine enabled tests based on type
        enabled = None
        if req.test_type == "spike": enabled = {"standard", "spike"}
        elif req.test_type == "scalability": enabled = {"standard", "scalability"}

        # NEW: Lighthouse audit progress stage
        from utils.lighthouse_comparator import LighthouseComparator
        if LighthouseComparator.is_available():
            progress_store[task_id].update({"percent": 25, "stage": "🔦 Running Lighthouse audit (ground truth)..."})
        
        # Perform the actual run - simulate progress jumps based on stages
        # Logic jump: Skip mobile/tablet as they aren't in current core.runner.py
        progress_store[task_id].update({"percent": 45, "stage": "Preparing suite..."})
        progress_store[task_id].update({"percent": 55, "stage": "Running baseline tests..."})
        
        # Perform the actual run
        res = await runner.run_all(
            enabled_tests=enabled,
            spike_requests=req.spike_requests or 0,
            scalability_plateau=req.scalability_plateau or 0
        )
        report_path, final_results = res if isinstance(res, tuple) else (res, {})

        # NEW: R&D DoS Stress Test (if enabled)
        if req.dos:
            from core.dos_tester import DoSTester
            
            def progress_logger(msg: str):
                # Update stage with the current wave info (must be sync — DoSTester calls self.log() synchronously)
                progress_store[task_id].update({"stage": f"🔴 {msg}"})
            
            progress_store[task_id].update({"percent": 90, "stage": "🔴 Initiating DoS Ramp (R&D Only)..."})
            tester = DoSTester(url=site.url, output_fn=progress_logger)
            dos_res = await tester.run_ramp(levels=[10, 50, 100, 200, 500, 1000, 2000], duration_per_level=8)
            
            main_mode = "authenticated" if isinstance(final_results, dict) and "authenticated" in final_results else "anonymous"
            if isinstance(final_results, dict) and main_mode in final_results:
                final_results[main_mode]["dos_results"] = dos_res
        
        progress_store[task_id].update({"percent": 98, "stage": "Generating visual HTML report..."})

        # Ensure the HTML report is actually generated on disk during dashboard runs
        from reporters.html_reporter import HTMLReporter
        try:
            HTMLReporter().generate(
                site_name=site.name, 
                site_url=site.url, 
                results=final_results if isinstance(final_results, dict) else {},
                output_path=report_path
            )
        except Exception as e:
            print(f"  [WARN] Dashboard failed to generate HTML Report: {e}")

        # Notify via Email with critical highlights
        if req.email_notification:
            main_mode = "authenticated" if "authenticated" in final_results else "anonymous"
            main_data = final_results.get(main_mode, {})
            if main_data:
                pub_url = f"http://localhost:9000/reports/{report_path.parent.name}/{report_path.name}"
                EmailService.send_report_alert(
                    recipient_email=req.email_notification,
                    site_name=site.name,
                    grade=main_data.get("grade", "N/A"),
                    report_url=pub_url,
                    spike=main_data.get("spike_results"),
                    stress=main_data.get("ramp_results")
                )
        
        # NEW: progress bar - Final State
        progress_store[task_id].update({
            "status": "complete", "percent": 100, "stage": "Complete",
            "report_url": f"/reports/{report_path.parent.name}/{report_path.name}"
        })
        
    except Exception as e:
        print(f"  [CRITICAL] Background Task Failed: {e}")
        if task_id in progress_store:
            progress_store[task_id].update({"status": "error", "error": str(e), "stage": "Failed"})


@router.post("/run-perf")
async def run_performance_test(req: PerfRequest, background_tasks: BackgroundTasks):
    """
    Triggers a performance sequence in the background.
    """
    # Generate Task ID for real-time progress bar tracking
    task_id = str(uuid.uuid4())
    report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_name = req.url.split("//")[-1].split("/")[0].replace(".", "_")
    expected_path = f"{datetime.now().strftime('%Y-%m-%d')}/{site_name}_report.html"
    
    background_tasks.add_task(_background_perf_task, req, report_id, task_id)
    
    return {
        "status": "scheduled",
        "task_id": task_id,
        "report_id": report_id,
        "expected_report": f"/reports/{expected_path}"
    }

@router.get("/report-status")
async def get_report_status(path: str):
    """Checks if a report file exists on disk."""
    # Use the clean relative path
    rel_path = path.replace("/reports/", "")
    full_path = REPORTS_DIR / rel_path
    exists = full_path.exists()
    return {
        "ready": exists,
        "url": path if exists else None
    }

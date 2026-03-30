from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import json
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


from utils.db_service import DBService

@router.get("/api/reports")
async def list_reports():
    """Lists all generated HTML reports from the database."""
    return DBService.get_all_reports()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    pool = BrowserPool.instance()
    return {
        "status": "healthy",
        "browser_running": pool.is_running,
        "timestamp": datetime.now().isoformat(),
    }


class PerfRequest(BaseModel):
    url: str
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    journey: Optional[List[Dict]] = None
    
    # New Fields for Enterprise Orchestration
    test_type: Optional[str] = "standard"  # standard, spike, soak, scalability
    spike_requests: Optional[int] = 0
    scalability_plateau: Optional[int] = 0
    email_notification: Optional[str] = None


async def _background_perf_task(req: PerfRequest, report_id: str):
    """
    Background worker that runs the test, generates the report, 
    and sends email notifications.
    """
    try:
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

        # Perform the actual run
        res = await runner.run_all(
            enabled_tests=enabled,
            spike_requests=req.spike_requests or 0,
            scalability_plateau=req.scalability_plateau or 0
        )
        report_path, final_results = res if isinstance(res, tuple) else (res, {})

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
    except Exception as e:
        print(f"  [CRITICAL] Background Task Failed: {e}")


@router.post("/run-perf")
async def run_performance_test(req: PerfRequest, background_tasks: BackgroundTasks):
    """
    Triggers a performance sequence in the background.
    """
    report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_name = req.url.split("//")[-1].split("/")[0].replace(".", "_")
    expected_path = f"{datetime.now().strftime('%Y-%m-%d')}/{site_name}_report.html"
    
    background_tasks.add_task(_background_perf_task, req, report_id)
    
    return {
        "status": "scheduled",
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

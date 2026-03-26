from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import json
from pathlib import Path

from core.runner import PerformanceRunner
from core.site_config import SiteConfig, Credentials
from utils.email_service import EmailService

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from locator_service.browser_pool import BrowserPool
from locator_service.cache import LocatorCache
from locator_service.scanner import PageScanner, ScanError
from locator_service.locator_generator import LocatorGenerator
from locator_service.models import ScanResponse

router = APIRouter()

# Shared instances (initialized at import, browser started via lifespan)
_cache = LocatorCache()
_scanner = PageScanner()
_generator = LocatorGenerator()


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


async def _background_perf_task(req: PerfRequest):
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
            
        runner = PerformanceRunner(site=site, headless=True)
        
        # Determine enabled tests based on type
        enabled = None
        if req.test_type == "spike": enabled = {"standard", "spike"}
        elif req.test_type == "scalability": enabled = {"standard", "scalability"}

        report_path = await runner.run_all(
            enabled_tests=enabled,
            spike_requests=req.spike_requests or 0,
            scalability_plateau=req.scalability_plateau or 0
        )

        # Notify via Email
        if req.email_notification:
            # Construct public link (assuming localhost for now)
            pub_url = f"http://localhost:8000/reports/{report_path.parent.name}/{report_path.name}"
            EmailService.send_report_alert(
                recipient_email=req.email_notification,
                site_name=site.name,
                grade="A", # TODO: Dynamically pull result grade
                report_url=pub_url
            )
            
    except Exception as e:
        print(f"  [CRITICAL] Background Task Failed: {e}")


@router.post("/run-perf")
async def run_performance_test(req: PerfRequest, background_tasks: BackgroundTasks):
    """
    Triggers a performance sequence in the background.
    Immediately returns a 'scheduled' status.
    """
    background_tasks.add_task(_background_perf_task, req)
    
    return {
        "status": "scheduled",
        "message": f"'{req.test_type}' test sequence initiated in background.",
        "notification": req.email_notification
    }

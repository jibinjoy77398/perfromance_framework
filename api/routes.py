"""
routes.py — API endpoints for the Locator Discovery service.
"""
from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

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

    - **url**: The page URL to scan
    - **force_refresh**: Set to true to bypass the cache
    - **include_hidden**: Set to true to include hidden elements

    Returns locator strategies ordered by priority:
    role → text → testid → id → css → xpath
    """
    # Validate URL
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Check cache first
    if not force_refresh:
        cached = await _cache.get(url)
        if cached:
            return cached

    # Fresh scan
    try:
        raw_elements, aria_tree = await _scanner.scan(url, include_hidden=include_hidden)
    except ScanError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    # Generate locators
    locators = _generator.generate_all(raw_elements, aria_tree)

    # Build response
    response = ScanResponse(
        url=url,
        source="fresh",
        scanned_at=datetime.now().isoformat(),
        element_count=len(locators),
        elements=locators,
    )

    # Cache the result
    await _cache.set(url, response)

    return response


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    pool = BrowserPool.instance()
    return {
        "status": "healthy",
        "browser_running": pool.is_running,
        "timestamp": datetime.now().isoformat(),
    }


@router.delete("/cache")
async def clear_cache(
    url: str = Query(None, description="Specific URL to clear, or omit for all"),
):
    """Clear cached scan results."""
    deleted = await _cache.clear(url)
    return {
        "cleared": deleted,
        "url": url or "all",
    }

"""
server.py — FastAPI application with browser lifecycle management.
Uses lifespan events to start/stop the shared browser pool.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI

from locator_service.browser_pool import BrowserPool
from locator_service.cache import LocatorCache
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser pool and cache lifecycle."""
    pool = BrowserPool.instance()
    cache = LocatorCache()

    # Startup
    print("\n🚀 Locator Discovery API — Starting")
    await pool.start()
    await cache.init()
    print("  ✅ Browser pool ready")
    print("  ✅ SQLite cache initialized")

    yield

    # Shutdown
    await pool.stop()
    print("  🛑 Locator Discovery API — Stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Locator Discovery API",
        description=(
            "Scans webpages, extracts interactive elements, "
            "and generates robust locators for Selenium/Playwright/pytest."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()

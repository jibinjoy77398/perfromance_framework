"""
server.py — FastAPI application with browser lifecycle management.
Uses lifespan events to start/stop the shared browser pool.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
load_dotenv() # Load local .env secrets

from locator_service.browser_pool import BrowserPool
from locator_service.cache import LocatorCache
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser pool and cache lifecycle."""
    pool = BrowserPool.instance()
    cache = LocatorCache()

    from helpers.db_service import DBService
    # Startup
    print("\n🚀 Performance Hub — Starting")
    DBService.init_db()
    await pool.start()
    await cache.init()
    print("  ✅ Browser pool ready")
    print("  ✅ SQLite cache initialized")
    print("  ✅ Results database initialized")

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
    
    # Ensure physical directories exist before mounting
    os.makedirs("reports", exist_ok=True)
    os.makedirs("web", exist_ok=True)
    
    app.mount("/reports", StaticFiles(directory="reports"), name="reports")
    app.mount("/static", StaticFiles(directory="web"), name="static")

    @app.get("/")
    def serve_dashboard():
        index_path = os.path.join("web", "index.html")
        if not os.path.exists(index_path):
            return {"error": "Dashboard index.html not found"}
        return FileResponse(index_path)

    return app


app = create_app()

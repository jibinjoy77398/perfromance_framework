"""
browser_pool.py — Singleton async browser lifecycle.
Reuses a single Chromium instance across all API requests for performance.
"""
from __future__ import annotations
from playwright.async_api import async_playwright, Browser, Page, Playwright


class BrowserPool:
    """
    Singleton browser pool — launches one Chromium instance and reuses it.

    Usage:
        pool = BrowserPool.instance()
        await pool.start()
        page = await pool.new_page()
        # ... use page ...
        await page.close()
        await pool.stop()
    """

    _instance: BrowserPool | None = None

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @classmethod
    def instance(cls) -> "BrowserPool":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def start(self) -> None:
        """Launch the shared browser. Call once at app startup."""
        if self.is_running:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-extensions",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )
        print("  🌐 BrowserPool: Chromium started")

    async def stop(self) -> None:
        """Close the shared browser. Call once at app shutdown."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        print("  🌐 BrowserPool: Chromium stopped")

    async def new_page(self) -> Page:
        """Create a fresh page in its own context from the shared browser."""
        if not self.is_running:
            await self.start()
        ctx = await self._browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
        )
        page = await ctx.new_page()
        return page

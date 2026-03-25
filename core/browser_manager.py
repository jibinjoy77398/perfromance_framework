"""
Browser Manager — launches a Playwright Chromium instance with CDP enabled.
"""
from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


NETWORK_PROFILES = {
    "Broadband": {
        "offline": False,
        "download_throughput": 5_000_000,   # bytes/s  (40 Mbps)
        "upload_throughput": 1_250_000,      # bytes/s  (10 Mbps)
        "latency": 0,
    },
    "4G": {
        "offline": False,
        "download_throughput": 2_500_000,    # 20 Mbps
        "upload_throughput": 1_250_000,      # 10 Mbps
        "latency": 20,
    },
    "Fast 3G": {
        "offline": False,
        "download_throughput": 187_500,      # 1.5 Mbps
        "upload_throughput": 93_750,         # 750 Kbps
        "latency": 40,
    },
    "Slow 3G": {
        "offline": False,
        "download_throughput": 62_500,       # 500 Kbps
        "upload_throughput": 62_500,
        "latency": 400,
    },
}


class BrowserManager:
    """Thin wrapper around Playwright that keeps a single browser process alive."""

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self._playwright = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=["--disable-extensions", "--no-sandbox"],
        )

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_context(self, network_profile: str | None = None) -> BrowserContext:
        """Create a new browser context, optionally throttled to a network profile."""
        ctx = await self._browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
        )
        if network_profile and network_profile in NETWORK_PROFILES:
            cdp = await ctx.new_cdp_session(await ctx.new_page())
            await cdp.send("Network.emulateNetworkConditions",
                           NETWORK_PROFILES[network_profile])
            await cdp.detach()
        return ctx

    async def new_page(self, network_profile: str | None = None) -> Page:
        """Return a fresh Page inside its own context."""
        ctx = await self._browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
        )
        page = await ctx.new_page()
        if network_profile and network_profile in NETWORK_PROFILES:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.emulateNetworkConditions",
                           NETWORK_PROFILES[network_profile])
        return page

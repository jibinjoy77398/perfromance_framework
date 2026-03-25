"""
conftest.py — pytest fixtures shared across all performance test modules.
Loads site config from config/sites.json and injects browser/page instances.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest_asyncio
from playwright.async_api import async_playwright

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sites.json"


def load_sites():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def pytest_generate_tests(metafunc):
    """Parametrize tests with all configured sites."""
    if "site" in metafunc.fixturenames:
        sites = load_sites()
        metafunc.parametrize("site", sites, ids=[s["name"] for s in sites])


@pytest_asyncio.fixture(scope="function")
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch(
            headless=True,
            args=["--disable-extensions", "--no-sandbox"],
        )
        yield b
        await b.close()


@pytest_asyncio.fixture(scope="function")
async def page(browser):
    ctx = await browser.new_context(ignore_https_errors=True)
    p = await ctx.new_page()
    yield p
    await ctx.close()

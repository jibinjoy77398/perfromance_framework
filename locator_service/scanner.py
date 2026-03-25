"""
scanner.py — Page scanning: extracts raw interactive elements + ARIA snapshot.
Queries only relevant elements (button, input, a, select, textarea) for performance.
"""
from __future__ import annotations
from playwright.async_api import Page

from locator_service.browser_pool import BrowserPool

# Only scan these tags for performance
SCAN_SELECTORS = "button, input, a, select, textarea"


class PageScanner:
    """
    Scans a webpage and extracts raw element data for locator generation.

    Usage:
        scanner = PageScanner()
        elements, aria_tree = await scanner.scan("https://example.com")
    """

    def __init__(self, pool: BrowserPool | None = None):
        self._pool = pool or BrowserPool.instance()

    async def scan(
        self,
        url: str,
        include_hidden: bool = False,
        timeout_ms: int = 30_000,
    ) -> tuple[list[dict], dict | None]:
        """
        Navigate to URL, extract interactive elements and ARIA tree.

        Returns:
            (elements_list, aria_tree)
            - elements_list: list of raw element dicts
            - aria_tree: accessibility snapshot (or None on error)
        """
        page = await self._pool.new_page()
        try:
            # Navigate and wait for page to be fully loaded
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            # Get accessibility tree for ARIA roles/names
            aria_tree = await self._get_aria_tree(page)

            # Extract interactive elements
            elements = await self._extract_elements(page, include_hidden)

            return elements, aria_tree
        except Exception as e:
            raise ScanError(f"Failed to scan {url}: {e}") from e
        finally:
            await page.context.close()

    async def _get_aria_tree(self, page: Page) -> dict | None:
        """Get the accessibility tree snapshot."""
        try:
            return await page.accessibility.snapshot()
        except Exception:
            return None

    async def _extract_elements(self, page: Page, include_hidden: bool) -> list[dict]:
        """Query all interactive elements and extract their data."""
        raw_elements = await page.evaluate(f"""
            () => {{
                const selector = "{SCAN_SELECTORS}";
                const nodes = document.querySelectorAll(selector);
                const results = [];

                for (const el of nodes) {{
                    const rect = el.getBoundingClientRect();
                    const isVisible = !!(
                        rect.width && rect.height &&
                        getComputedStyle(el).visibility !== 'hidden' &&
                        getComputedStyle(el).display !== 'none' &&
                        el.offsetParent !== null
                    );

                    // Skip hidden unless explicitly requested
                    if (!isVisible && !{str(include_hidden).lower()}) continue;

                    // Collect all attributes
                    const attrs = {{}};
                    for (const attr of el.attributes) {{
                        attrs[attr.name] = attr.value;
                    }}

                    results.push({{
                        tag: el.tagName.toLowerCase(),
                        visible_text: (el.innerText || el.textContent || '').trim().substring(0, 200),
                        attributes: attrs,
                        is_visible: isVisible,
                        bounding_box: {{
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        }},
                        // Additional useful properties
                        input_type: el.type || null,
                        aria_role: el.getAttribute('role') || el.tagName.toLowerCase(),
                        aria_label: el.getAttribute('aria-label') || null,
                        placeholder: el.getAttribute('placeholder') || null,
                        href: el.href || null,
                    }});
                }}
                return results;
            }}
        """)
        return raw_elements


class ScanError(Exception):
    """Raised when page scanning fails."""
    pass

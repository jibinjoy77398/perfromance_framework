import asyncio
from playwright.async_api import Page

async def detect_site_type(page: Page) -> dict:
    """
    Fingerprints the site and returns a plan signals dictionary.
    Decides if it's a search site, form site, or static.
    Also detects if it's likely a CSR (Client-Side Rendered) app.
    """
    signals = {
        "has_search": False,
        "has_auth": False,
        "has_form": False,
        "is_csr": False,
        "type": "static_site",
        "selector": None
    }
    
    try:
        # 1. Detect CSR vs SSR (thin shell = CSR)
        html = await page.content()
        signals["is_csr"] = len(html) < 4000 # Increased threshold for modern apps
        
        # 2. Check for Extractor (URL-based processor)
        extractor_selectors = [
            'input[placeholder*=".com" i]',
            'input[placeholder*="domain" i]',
            'input[placeholder*="url" i]',
            'input[placeholder*="http" i]'
        ]
        button_extractor_text = ["Analyze", "Extract", "Inspect", "Try It Now", "Get Started"]
        
        for sel in extractor_selectors:
            if await page.query_selector(sel):
                # Double check if any button nearby confirms it's an extractor
                buttons = await page.query_selector_all('button, a[role="button"]')
                for btn in buttons:
                     txt = await btn.inner_text()
                     if any(k.lower() in txt.lower() for k in button_extractor_text):
                         signals["has_search"] = True
                         signals["type"] = "extractor_site"
                         signals["selector"] = sel
                         break
                if signals["type"] == "extractor_site": break

        # 3. Check for Search (Generic)
        if signals["type"] == "static_site":
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="search" i]', 
                'input[name*="search" i]',
                'input[id*="search" i]',
                '[aria-label*="search" i]'
            ]
            for sel in search_selectors:
                if await page.query_selector(sel):
                    signals["has_search"] = True
                    signals["type"] = "search_site"
                    signals["selector"] = sel
                    break
                
        # 4. Check for Auth
        auth_selectors = [
            'input[type="password"]',
            'a[href*="login" i]',
            'a[href*="signin" i]',
            'button:has-text("Login")',
            'button:has-text("Sign In")'
        ]
        for sel in auth_selectors:
            if await page.query_selector(sel):
                signals["has_auth"] = True
                if signals["type"] == "static_site":
                    signals["type"] = "auth_site"
                    signals["selector"] = sel
                break

        # 4. Check for Forms
        form_elements = await page.query_selector_all('input:not([type="hidden"]), textarea, select')
        if len(form_elements) >= 3:
            signals["has_form"] = True
            if signals["type"] == "static_site":
                signals["type"] = "form_site"
                signals["selector"] = "form" if await page.query_selector("form") else "body"

        return signals

    except Exception as e:
        print(f"  [WARN] Site fingerprinting failed: {e}")
        return signals

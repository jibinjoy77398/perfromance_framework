"""
BasePage — POM base class. All pages inherit from this.
Automatically hooks into navigation to collect performance metrics.
"""
from __future__ import annotations
from playwright.async_api import Page
from core.metrics_collector import MetricsCollector


class BasePage:
    """
    Every page object inherits BasePage.
    Usage:
        page_obj = BasePage(page, "https://mysite.com", login_url="https://mysite.com/login")
        await page_obj.setup()
        await page_obj.navigate()
        metrics = await page_obj.get_metrics()
    """

    def __init__(self, page: Page, url: str, login_url: str | None = None):
        self.page = page
        self.url = url
        self.login_url = login_url
        self._collector = MetricsCollector(page)

    async def setup(self) -> None:
        """Call once after creating the page object."""
        await self._collector.setup()

    async def navigate(self, url: str | None = None) -> None:
        """Navigate to the page URL (or an override)."""
        target = url or self.url
        await self.page.goto(target, wait_until="domcontentloaded", timeout=60_000)

    async def login(self, username: str, password: str,
                    username_selector: str = "input[type='email'], input[name='username'], input[name='email'], #username, #email",
                    password_selector: str = "input[type='password'], #password",
                    submit_selector: str = "button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign in')"
                    ) -> float:
        """
        Generic login — tries common selectors automatically.
        If login_url is set, navigates there first before filling the form.
        Override in a subclass if the site has a non-standard form.
        """
        try:
            target_url = self.login_url or self.url
            if self.login_url:
                await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=60_000)

            # --- Locator Discovery Cache Integration ---
            try:
                from locator_service.cache import LocatorCache
                cache = LocatorCache()
                cached = await cache.get(target_url)
                if cached:
                    best_u, best_p, best_s = None, None, None
                    
                    def get_selector(el):
                        # Returns a valid page.locator() string from the element's strategies
                        for s in el.strategies:
                            if s.method in ("css", "id", "xpath", "testid"):
                                if s.method == "testid":
                                    return f"[data-testid='{s.value}']"
                                return s.value
                        return el.preferred.value if el.preferred else ""

                    for el in cached.elements:
                        attrs = el.attributes
                        typ, name = attrs.get("type", "").lower(), attrs.get("name", "").lower()
                        # Password
                        if typ == "password" and not best_p:
                            best_p = get_selector(el)
                        # Username
                        elif (typ == "email" or "user" in name or "email" in name) and not best_u:
                            best_u = get_selector(el)
                        # Submit
                        elif ((el.tag in ["button", "input"] and typ == "submit") or 
                              (el.tag == "button" and any(w in (el.visible_text or "").lower() for w in ["login", "sign in"]))):
                            if not best_s:
                                best_s = get_selector(el)

                    if best_u: username_selector = best_u
                    if best_p: password_selector = best_p
                    if best_s: submit_selector = best_s
                    print(f"  [INFO] Using discovered locators: user={username_selector}, pass={password_selector}, submit={submit_selector}")
            except Exception as cache_err:
                print(f"  [DEBUG] LocatorCache check failed: {cache_err}")
            # ---------------------------------------------

            await self.page.locator(username_selector).first.fill(username)
            await self.page.locator(password_selector).first.fill(password)
            import time
            start_time = time.perf_counter()
            await self.page.locator(submit_selector).first.click()
            
            # Wait for specific target url if we logged in via a separate login_url
            if self.login_url and self.url != self.login_url:
                try:
                    await self.page.wait_for_url(self.url, timeout=15_000)
                except Exception:
                    pass
                    
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
                
            return (time.perf_counter() - start_time) * 1000.0
        except Exception as e:
            print(f"  [WARN] Login attempt failed: {e}")
            return 0.0

    async def run_journey(self, journey: list[dict]) -> None:
        """Executes a custom array of automation interactions sequentially."""
        print(f"  [INFO] Initiating custom {len(journey)}-step automation journey...")
        for step in journey:
            action = step.get("action", "").lower()
            selector = step.get("selector", "")
            value = step.get("value", "")
            timeout = int(step.get("timeout", 10000))
            
            try:
                # ── Mouse & Interaction ──
                if action == "click":
                    await self.page.locator(selector).first.click(timeout=timeout)
                elif action == "dblclick":
                    await self.page.locator(selector).first.dblclick(timeout=timeout)
                elif action == "hover":
                    await self.page.locator(selector).first.hover(timeout=timeout)
                elif action == "check":
                    await self.page.locator(selector).first.check(timeout=timeout)
                elif action == "uncheck":
                    await self.page.locator(selector).first.uncheck(timeout=timeout)
                elif action == "select":
                    await self.page.locator(selector).first.select_option(value, timeout=timeout)
                elif action == "scroll_into_view":
                    await self.page.locator(selector).first.scroll_into_view_if_needed(timeout=timeout)
                
                # ── Keyboard & Input ──
                elif action == "fill":
                    await self.page.locator(selector).first.fill(value, timeout=timeout)
                elif action == "type" or action == "press_sequentially":
                    delay = int(step.get("delay", 0))
                    await self.page.locator(selector).first.press_sequentially(value, delay=delay, timeout=timeout)
                elif action == "press":
                    key = step.get("key", "Enter")
                    if selector:
                        await self.page.locator(selector).first.press(key, timeout=timeout)
                    else:
                        await self.page.keyboard.press(key)
                
                # ── Navigation & Waiting ──
                elif action == "navigate" or action == "goto":
                    await self.page.goto(value, wait_until="domcontentloaded", timeout=timeout)
                elif action == "wait_for_selector":
                    state = step.get("state", "visible")
                    await self.page.wait_for_selector(selector, state=state, timeout=timeout)
                elif action == "wait_for_url":
                    await self.page.wait_for_url(value, timeout=timeout)
                elif action == "wait":
                    delay_ms = int(step.get("duration", step.get("timeout", 1000)))
                    await self.page.wait_for_timeout(delay_ms)
                    
            except Exception as e:
                print(f"  [WARN] Journey Step Error ({action} on {selector or value}): {e}")

    async def get_metrics(self) -> dict:
        """Collect and return all performance metrics for the current page."""
        return await self._collector.collect()

    async def scroll_to_bottom(self) -> None:
        """Scroll page slowly to trigger lazy-loaded resources and CLS."""
        try:
            await self.page.evaluate("""
                async () => {
                    await new Promise(resolve => {
                        let total = document.body.scrollHeight;
                        let current = 0;
                        const step = Math.max(100, total / 20);
                        const timer = setInterval(() => {
                            window.scrollBy(0, step);
                            current += step;
                            if (current >= total) { clearInterval(timer); resolve(); }
                        }, 100);
                    });
                }
            """)
            await self.page.wait_for_timeout(500)
        except Exception as e:
            # Flaky single page applications might navigate mid-scroll, which destroys the JS context.
            print(f"  [DEBUG] Scroll sequence interrupted by navigation: {e}")

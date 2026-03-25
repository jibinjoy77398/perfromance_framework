"""
LoginPage — Subclass of BasePage for sites with non-standard login forms.
Demonstrates inheritance: override login() for custom flows.
"""
from __future__ import annotations
from pages.base_page import BasePage


class LoginPage(BasePage):
    """
    Override this class for sites with non-standard login forms.
    The default BasePage.login() handles common selectors, but if a site
    uses a multi-step login, OTP, or custom elements, subclass LoginPage.

    Example:
        class MyAppLoginPage(LoginPage):
            async def login(self, username, password):
                await self.page.fill("#custom-email", username)
                await self.page.click("#next-btn")
                await self.page.wait_for_selector("#password-step")
                await self.page.fill("#custom-pass", password)
                await self.page.click("#sign-in")
                await self.page.wait_for_load_state("networkidle")
    """

    def __init__(self, page, url: str, login_url: str | None = None,
                 username_selector: str = "input[type='email'], input[name='username'], input[name='email'], #username, #email",
                 password_selector: str = "input[type='password'], #password",
                 submit_selector: str = "button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign in')"):
        super().__init__(page, url, login_url=login_url)
        self._username_selector = username_selector
        self._password_selector = password_selector
        self._submit_selector = submit_selector

    async def login(self, username: str, password: str, **kwargs) -> None:
        """
        Login using the configured selectors.
        Override this method in subclasses for custom login flows.
        """
        try:
            if self.login_url:
                await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=60_000)

            await self.page.locator(self._username_selector).first.fill(username)
            await self.page.locator(self._password_selector).first.fill(password)
            await self.page.locator(self._submit_selector).first.click()
            await self.page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception as e:
            print(f"  [WARN] LoginPage.login() failed: {e}")

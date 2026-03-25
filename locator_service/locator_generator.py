"""
locator_generator.py — Generates all possible locator strategies per element.
Replicates Playwright codegen's priority logic: role > text > testid > id > css > xpath.
"""
from __future__ import annotations
from locator_service.models import LocatorStrategy, ElementLocator


class LocatorGenerator:
    """
    Generates locator strategies for raw element data.
    Each element gets multiple strategies ordered by priority,
    with the best unique one marked as 'preferred'.

    Usage:
        generator = LocatorGenerator()
        locators = generator.generate_all(raw_elements, aria_tree)
    """

    # Priority order (same as Playwright codegen)
    STRATEGY_ORDER = ["role", "text", "testid", "id", "css", "xpath"]

    def generate_all(
        self, raw_elements: list[dict], aria_tree: dict | None = None
    ) -> list[ElementLocator]:
        """Generate locator objects for all scanned elements."""
        # Build lookup tables for uniqueness checks
        all_ids = self._count_values(raw_elements, "id")
        all_testids = self._count_values(raw_elements, "data-testid")
        all_texts = self._count_texts(raw_elements)

        locators = []
        for el in raw_elements:
            strategies = self._build_strategies(el, all_ids, all_testids, all_texts)
            preferred = self._pick_preferred(strategies)

            locators.append(ElementLocator(
                tag=el.get("tag", ""),
                visible_text=el.get("visible_text") or None,
                attributes=el.get("attributes", {}),
                is_visible=el.get("is_visible", True),
                bounding_box=el.get("bounding_box"),
                aria_role=el.get("aria_role"),
                aria_name=el.get("aria_label"),
                strategies=strategies,
                preferred=preferred,
            ))
        return locators

    # ── Strategy builders ────────────────────────────────────────────────

    def _build_strategies(
        self, el: dict, all_ids: dict, all_testids: dict, all_texts: dict
    ) -> list[LocatorStrategy]:
        """Build all strategies for a single element, in priority order."""
        strategies: list[LocatorStrategy] = []
        tag = el.get("tag", "")
        attrs = el.get("attributes", {})
        text = (el.get("visible_text") or "").strip()

        # 1. Role-based (getByRole)
        role = self._map_role(tag, attrs)
        name = el.get("aria_label") or text
        if role and name:
            confidence = 0.9  # role + name is usually unique
            strategies.append(LocatorStrategy(
                method="role",
                value=f'role={role}, name="{self._escape(name[:60])}"',
                confidence=confidence,
                framework_hint={
                    "playwright": f'page.get_by_role("{role}", name="{self._escape(name[:60])}")',
                    "selenium": f"driver.find_element(By.XPATH, '//{tag}[@role=\"{role}\" or self::{tag}'][normalize-space()=\"{self._escape(name[:60])}\"]')",
                },
            ))

        # 2. Text-based (getByText)
        if text and len(text) <= 80:
            txt_count = all_texts.get(text, 0)
            confidence = 1.0 if txt_count == 1 else max(0.3, 1.0 - txt_count * 0.2)
            strategies.append(LocatorStrategy(
                method="text",
                value=f'"{self._escape(text[:80])}"',
                confidence=confidence,
                framework_hint={
                    "playwright": f'page.get_by_text("{self._escape(text[:80])}")',
                    "selenium": f"driver.find_element(By.XPATH, '//*[normalize-space()=\"{self._escape(text[:80])}\"]')",
                },
            ))

        # 3. data-testid
        testid = attrs.get("data-testid")
        if testid:
            tid_count = all_testids.get(testid, 0)
            confidence = 1.0 if tid_count == 1 else 0.5
            strategies.append(LocatorStrategy(
                method="testid",
                value=testid,
                confidence=confidence,
                framework_hint={
                    "playwright": f'page.get_by_test_id("{testid}")',
                    "selenium": f"driver.find_element(By.CSS_SELECTOR, '[data-testid=\"{testid}\"]')",
                },
            ))

        # 4. ID
        elem_id = attrs.get("id")
        if elem_id:
            id_count = all_ids.get(elem_id, 0)
            confidence = 1.0 if id_count == 1 else 0.4
            strategies.append(LocatorStrategy(
                method="id",
                value=f"#{elem_id}",
                confidence=confidence,
                framework_hint={
                    "playwright": f'page.locator("#{elem_id}")',
                    "selenium": f'driver.find_element(By.ID, "{elem_id}")',
                },
            ))

        # 5. CSS selector
        css = self._build_css(tag, attrs)
        strategies.append(LocatorStrategy(
            method="css",
            value=css,
            confidence=0.6,
            framework_hint={
                "playwright": f'page.locator("{css}")',
                "selenium": f"driver.find_element(By.CSS_SELECTOR, '{css}')",
            },
        ))

        # 6. XPath (fallback)
        xpath = self._build_xpath(tag, attrs, text)
        strategies.append(LocatorStrategy(
            method="xpath",
            value=xpath,
            confidence=0.4,
            framework_hint={
                "playwright": f'page.locator("xpath={xpath}")',
                "selenium": f"driver.find_element(By.XPATH, '{xpath}')",
            },
        ))

        return strategies

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _map_role(tag: str, attrs: dict) -> str | None:
        """Map HTML tag to ARIA role."""
        explicit_role = attrs.get("role")
        if explicit_role:
            return explicit_role
        role_map = {
            "button": "button",
            "a": "link",
            "input": None,  # depends on type
            "select": "combobox",
            "textarea": "textbox",
        }
        if tag == "input":
            input_type = attrs.get("type", "text")
            input_roles = {
                "text": "textbox", "email": "textbox", "search": "searchbox",
                "password": "textbox", "tel": "textbox", "url": "textbox",
                "number": "spinbutton", "checkbox": "checkbox", "radio": "radio",
                "submit": "button", "reset": "button", "button": "button",
            }
            return input_roles.get(input_type, "textbox")
        return role_map.get(tag)

    @staticmethod
    def _build_css(tag: str, attrs: dict) -> str:
        """Build a CSS selector from tag + key attributes."""
        parts = [tag]
        if attrs.get("id"):
            parts.append(f"#{attrs['id']}")
        elif attrs.get("type"):
            parts.append(f"[type='{attrs['type']}']")
        if attrs.get("name"):
            parts.append(f"[name='{attrs['name']}']")
        elif attrs.get("class"):
            # Use first class only
            first_cls = attrs["class"].split()[0]
            parts.append(f".{first_cls}")
        return "".join(parts)

    @staticmethod
    def _build_xpath(tag: str, attrs: dict, text: str) -> str:
        """Build an XPath selector."""
        predicates = []
        if attrs.get("id"):
            predicates.append(f"@id='{attrs['id']}'")
        elif attrs.get("name"):
            predicates.append(f"@name='{attrs['name']}'")
        elif attrs.get("type"):
            predicates.append(f"@type='{attrs['type']}'")
        if text and len(text) <= 50:
            predicates.append(f"normalize-space()='{text[:50]}'")
        pred_str = " and ".join(predicates) if predicates else ""
        return f"//{tag}[{pred_str}]" if pred_str else f"//{tag}"

    @staticmethod
    def _pick_preferred(strategies: list[LocatorStrategy]) -> LocatorStrategy | None:
        """Pick the highest-priority strategy with confidence >= 0.8."""
        for s in strategies:
            if s.confidence >= 0.8:
                return s
        # If none are high-confidence, return the first one
        return strategies[0] if strategies else None

    @staticmethod
    def _count_values(elements: list[dict], attr_name: str) -> dict[str, int]:
        """Count how many elements share the same attribute value."""
        counts: dict[str, int] = {}
        for el in elements:
            val = el.get("attributes", {}).get(attr_name)
            if val:
                counts[val] = counts.get(val, 0) + 1
        return counts

    @staticmethod
    def _count_texts(elements: list[dict]) -> dict[str, int]:
        """Count how many elements share the same visible text."""
        counts: dict[str, int] = {}
        for el in elements:
            text = (el.get("visible_text") or "").strip()
            if text:
                counts[text] = counts.get(text, 0) + 1
        return counts

    @staticmethod
    def _escape(s: str) -> str:
        """Escape quotes for use in locator strings."""
        return s.replace('"', '\\"').replace("'", "\\'")

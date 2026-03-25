"""
models.py — Pydantic schemas for the Locator Discovery API.
Defines the structure of locator strategies, element locators, and scan responses.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class LocatorStrategy(BaseModel):
    """
    A single locator strategy for an element.

    Attributes:
        method: Strategy type — "role", "text", "testid", "id", "css", "xpath"
        value: The locator string (e.g., "button", "#login-btn")
        confidence: 0.0–1.0 uniqueness score (1.0 = guaranteed unique on page)
        framework_hint: Ready-to-use locator strings per framework
    """
    method: str
    value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    framework_hint: dict = Field(default_factory=dict)


class ElementLocator(BaseModel):
    """
    A single interactive element discovered on the page.

    Contains all possible locator strategies, ordered by priority.
    The 'preferred' field is the best strategy based on uniqueness and stability.
    """
    tag: str
    visible_text: Optional[str] = None
    attributes: dict = Field(default_factory=dict)
    is_visible: bool = True
    bounding_box: Optional[dict] = None
    aria_role: Optional[str] = None
    aria_name: Optional[str] = None
    strategies: list[LocatorStrategy] = Field(default_factory=list)
    preferred: Optional[LocatorStrategy] = None


class ScanRequest(BaseModel):
    """Request body for POST /scan."""
    url: str
    force_refresh: bool = False
    include_hidden: bool = False


class ScanResponse(BaseModel):
    """Full response from the /scan endpoint."""
    url: str
    source: str = "fresh"  # "cache" or "fresh"
    scanned_at: str = ""
    element_count: int = 0
    elements: list[ElementLocator] = Field(default_factory=list)

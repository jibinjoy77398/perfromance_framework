"""
SiteConfig — Typed dataclass replacing raw dict for site configuration.
Encapsulates site name, URL, login URL, and credentials in one object.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Credentials:
    """Login credentials for a site."""
    username: str
    password: str


@dataclass
class SiteConfig:
    """
    Encapsulates all configuration for a single site under test.

    Usage:
        sites = SiteConfig.load_all(Path("config/sites.json"))
        for site in sites:
            print(site.name, site.url)
    """
    name: str
    url: str
    login_url: Optional[str] = None
    credentials: Optional[Credentials] = None
    journey: Optional[list[dict]] = None

    # ── Factory methods ──────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "SiteConfig":
        """Create a SiteConfig from a JSON-style dictionary."""
        creds = data.get("credentials")
        return cls(
            name=data["name"],
            url=data["url"],
            login_url=data.get("login_url"),
            credentials=Credentials(**creds) if creds else None,
            journey=data.get("journey"),
        )

    @classmethod
    def load_all(cls, path: Path) -> list["SiteConfig"]:
        """Load all sites from a JSON config file."""
        with open(path) as f:
            raw = json.load(f)
        return [cls.from_dict(entry) for entry in raw]

    # ── Convenience ──────────────────────────────────────────────────────

    @property
    def has_credentials(self) -> bool:
        return self.credentials is not None

    def to_dict(self) -> dict:
        """Convert back to a plain dict (useful for backward compatibility)."""
        d: dict = {"name": self.name, "url": self.url}
        if self.login_url:
            d["login_url"] = self.login_url
        if self.credentials:
            d["credentials"] = {
                "username": self.credentials.username,
                "password": self.credentials.password,
            }
        else:
            d["credentials"] = None
        return d

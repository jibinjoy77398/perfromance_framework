"""
cache.py — SQLite async cache for locator scan results.
Uses aiosqlite for non-blocking database access.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite

from locator_service.models import ScanResponse

DB_PATH = Path(__file__).parent.parent / "config" / "locator_cache.db"
DEFAULT_TTL_HOURS = 24


class LocatorCache:
    """
    Async SQLite cache for scan results.

    Usage:
        cache = LocatorCache()
        await cache.init()
        cached = await cache.get("https://example.com")
        await cache.set("https://example.com", scan_response)
    """

    def __init__(self, db_path: Path | None = None, ttl_hours: int = DEFAULT_TTL_HOURS):
        self._db_path = str(db_path or DB_PATH)
        self._ttl_hours = ttl_hours

    async def init(self) -> None:
        """Create the cache table if it doesn't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS locator_cache (
                    url TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    scanned_at TEXT NOT NULL
                )
            """)
            await db.commit()

    async def get(self, url: str) -> ScanResponse | None:
        """Retrieve cached response if it exists and hasn't expired."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT response_json, scanned_at FROM locator_cache WHERE url = ?",
                (url,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        response_json, scanned_at = row

        # Check TTL
        scanned_dt = datetime.fromisoformat(scanned_at)
        if datetime.now() - scanned_dt > timedelta(hours=self._ttl_hours):
            return None  # Expired

        data = json.loads(response_json)
        response = ScanResponse(**data)
        response.source = "cache"
        return response

    async def set(self, url: str, response: ScanResponse) -> None:
        """Store or update a scan response."""
        now = datetime.now().isoformat()
        response.scanned_at = now
        response_json = response.model_dump_json()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO locator_cache (url, response_json, scanned_at)
                VALUES (?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    response_json = excluded.response_json,
                    scanned_at = excluded.scanned_at
                """,
                (url, response_json, now),
            )
            await db.commit()

    async def clear(self, url: str | None = None) -> int:
        """Clear one or all cache entries. Returns number of rows deleted."""
        async with aiosqlite.connect(self._db_path) as db:
            if url:
                cursor = await db.execute("DELETE FROM locator_cache WHERE url = ?", (url,))
            else:
                cursor = await db.execute("DELETE FROM locator_cache")
            await db.commit()
            return cursor.rowcount

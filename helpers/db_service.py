import sqlite3
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Optional: Supabase integration
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

load_dotenv()

class DBService:
    DB_PATH = Path("database/results.db")
    _supabase: Client = None

    @classmethod
    def _get_supabase(cls) -> Client:
        """Initializes and returns the Supabase client safely."""
        if not SUPABASE_AVAILABLE:
            return None
        
        if cls._supabase is None:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                try:
                    cls._supabase = create_client(url, key)
                except Exception as e:
                    print(f"  [WARN] Supabase init failed: {e}")
        return cls._supabase

    @classmethod
    def init_db(cls):
        """Initializes the SQLite database and handles schema migrations."""
        os.makedirs(cls.DB_PATH.parent, exist_ok=True)
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()
        
        # 1. Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                site TEXT,
                date TEXT,
                url TEXT,
                grade TEXT,
                passed INTEGER,
                failed INTEGER,
                duration REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Schema Migration: Add missing columns if they don't exist
        cursor.execute("PRAGMA table_info(reports)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        needed_columns = {
            "interaction_type": "TEXT DEFAULT 'none'",
            "interaction_time_ms": "INTEGER DEFAULT 0",
            "search_response_ms": "INTEGER DEFAULT 0",
            "js_errors": "INTEGER DEFAULT 0",
            "network_requests": "INTEGER DEFAULT 0",
            "network_bytes_kb": "REAL DEFAULT 0.0",
            "interaction_p95_ms": "INTEGER DEFAULT 0",
            "interaction_avg_ms": "REAL DEFAULT 0.0",
            "interaction_count": "INTEGER DEFAULT 1"
        }
        
        for col, col_def in needed_columns.items():
            if col not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_def}")
                    print(f"  [INFO] Database Migrated: Added column '{col}' to 'reports' table.")
                except Exception as e:
                    print(f"  [WARN] Migration failed for column '{col}': {e}")
        
        conn.commit()
        conn.close()

    @classmethod
    def log_report(cls, name, site, date, url, grade="N/A", passed=0, failed=0, duration=0.0, **kwargs):
        """Inserts a new report record into SQLite and Supabase."""
        interaction_type = kwargs.get("interaction_type", "none")
        interaction_time_ms = kwargs.get("interaction_time_ms", 0)
        search_response_ms = kwargs.get("search_response_ms", 0)
        js_errors = kwargs.get("js_errors", 0)
        network_requests = kwargs.get("network_requests", 0)
        network_bytes_kb = kwargs.get("network_bytes_kb", 0.0)
        interaction_p95_ms = kwargs.get("interaction_p95_ms", 0)
        interaction_avg_ms = kwargs.get("interaction_avg_ms", 0.0)
        interaction_count = kwargs.get("interaction_count", 1)

        # 1. Local SQLite logging (Primary)
        try:
            conn = sqlite3.connect(cls.DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reports (
                    name, site, date, url, grade, passed, failed, duration,
                    interaction_type, interaction_time_ms, search_response_ms, js_errors,
                    network_requests, network_bytes_kb, interaction_p95_ms, interaction_avg_ms,
                    interaction_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, site, date, url, grade, passed, failed, duration,
                interaction_type, interaction_time_ms, search_response_ms, js_errors,
                network_requests, network_bytes_kb, interaction_p95_ms, interaction_avg_ms,
                interaction_count
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  [WARN] Failed to log locally: {e}")

        # 2. Supabase Cloud logging (Secondary)
        sb = cls._get_supabase()
        if sb:
            try:
                data = {
                    "name": name,
                    "site": site,
                    "date": date,
                    "url": url,
                    "grade": grade,
                    "passed": passed,
                    "failed": failed,
                    "duration": duration,
                    "interaction_type": interaction_type,
                    "interaction_time_ms": interaction_time_ms,
                    "search_response_ms": search_response_ms,
                    "js_errors": js_errors,
                    "network_requests": network_requests,
                    "network_bytes_kb": network_bytes_kb,
                    "interaction_p95_ms": interaction_p95_ms,
                    "interaction_avg_ms": interaction_avg_ms,
                    "interaction_count": interaction_count
                }
                sb.table("reports").insert(data).execute()
                print(f"  [INFO] Logged to Supabase cloud successfully.")
            except Exception as e:
                print(f"  [WARN] Failed to log to Supabase: {e}")

    @classmethod
    def get_all_reports(cls):
        """Fetches unified report records, prioritizing Supabase cloud data."""
        # 1. Try Supabase Cloud
        sb = cls._get_supabase()
        if sb:
            try:
                response = sb.table("reports").select("*").order("timestamp", desc=True).execute()
                if response.data:
                    return response.data
            except Exception as e:
                print(f"  [WARN] Supabase fetch failed, falling back to local: {e}")

        # 2. Fallback to Local SQLite
        if not cls.DB_PATH.exists():
            return []
        
        try:
            conn = sqlite3.connect(cls.DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reports ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"  [ERROR] Database fetch failed: {e}")
            return []

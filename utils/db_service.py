import sqlite3
import os
from pathlib import Path
from datetime import datetime

class DBService:
    DB_PATH = Path("database/results.db")

    @classmethod
    def init_db(cls):
        """Initializes the SQLite database and creates the reports table."""
        os.makedirs(cls.DB_PATH.parent, exist_ok=True)
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()
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
        conn.commit()
        conn.close()

    @classmethod
    def log_report(cls, name, site, date, url, grade="N/A", passed=0, failed=0, duration=0.0):
        """Inserts a new report record into the database."""
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reports (name, site, date, url, grade, passed, failed, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, site, date, url, grade, passed, failed, duration))
        conn.commit()
        conn.close()

    @classmethod
    def get_all_reports(cls):
        """Fetches all report records, sorted by timestamp descending."""
        if not cls.DB_PATH.exists():
            return []
        conn = sqlite3.connect(cls.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

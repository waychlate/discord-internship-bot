import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from src.models import JobPosting


class Database:
    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = db_path
        self._ensure_dir()
        self.init_db()

    def _ensure_dir(self):
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    id TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    location TEXT,
                    source TEXT,
                    matched_keywords TEXT,
                    terms TEXT,
                    sponsorship TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_jobs_company ON seen_jobs(company);"
            )
            conn.commit()

    def is_job_seen(self, job_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_jobs WHERE id = ?", (job_id,))
            return cursor.fetchone() is not None

    def save_job(self, job: JobPosting) -> bool:
        """Save a new job. Returns True if inserted, False if already exists."""
        if self.is_job_seen(job.id):
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO seen_jobs 
                (id, company, title, url, location, source, matched_keywords, terms, sponsorship, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.company,
                    job.title,
                    job.url,
                    job.location,
                    job.source,
                    ", ".join(job.matched_keywords),
                    job.terms or "",
                    job.sponsorship or "",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_total_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM seen_jobs")
            return cursor.fetchone()[0]


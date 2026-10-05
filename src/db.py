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
            # Migrations for DBs created before the pending queue existed
            cols = {r["name"] for r in cursor.execute("PRAGMA table_info(seen_jobs)")}
            if "status" not in cols:  # 'pending' = queued for Discord, 'sent', or 'seen' (indexed silently)
                cursor.execute("ALTER TABLE seen_jobs ADD COLUMN status TEXT DEFAULT 'sent'")
            if "dedup_key" not in cols:
                cursor.execute("ALTER TABLE seen_jobs ADD COLUMN dedup_key TEXT")
            if "date_posted" not in cols:
                cursor.execute("ALTER TABLE seen_jobs ADD COLUMN date_posted TEXT")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_jobs_company ON seen_jobs(company);"
            )
            conn.commit()

    def is_job_seen(self, job_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_jobs WHERE id = ?", (job_id,))
            return cursor.fetchone() is not None

    def is_duplicate(self, job: JobPosting) -> bool:
        """Seen before, by exact id or by the job id inside its URL (same posting on another list)."""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT 1 FROM seen_jobs WHERE id = ? OR dedup_key = ?", (job.id, job.dedup_key)
            ).fetchone() is not None

    def save_job(self, job: JobPosting, status: str = "sent") -> bool:
        """Save a new job. Returns True if inserted, False if already exists."""
        if self.is_job_seen(job.id):
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO seen_jobs 
                (id, company, title, url, location, source, matched_keywords, terms, sponsorship, first_seen_at, status, date_posted, dedup_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    status,
                    job.date_posted,
                    job.dedup_key,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_total_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM seen_jobs")
            return cursor.fetchone()[0]


    def pending_count(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE status = 'pending'").fetchone()[0]

    def pending_batch(self, limit: int) -> List[JobPosting]:
        """Oldest queued jobs, up to `limit`."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM seen_jobs WHERE status = 'pending' ORDER BY first_seen_at, rowid LIMIT ?", (limit,)
            ).fetchall()
        return [
            JobPosting(
                company=r["company"],
                title=r["title"],
                url=r["url"],
                location=r["location"] or "Not specified",
                source=r["source"] or "Unknown",
                date_posted=r["date_posted"] or None,
                matched_keywords=[k for k in (r["matched_keywords"] or "").split(", ") if k],
                terms=r["terms"] or None,
            )
            for r in rows
        ]

    def mark_sent(self, job_id: str, status: str = "sent"):
        with self.get_connection() as conn:
            conn.execute("UPDATE seen_jobs SET status = ? WHERE id = ?", (status, job_id))
            conn.commit()

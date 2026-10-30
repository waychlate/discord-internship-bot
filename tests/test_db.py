import os
import sqlite3
import tempfile
import unittest
from src.db import Database
from src.models import JobPosting


class TestDatabase(unittest.TestCase):
    def setUp(self):
        fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.temp_path)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.remove(self.temp_path)

    def test_database_insert_and_deduplication(self):
        job1 = JobPosting(
            company="SpaceX",
            title="Silicon Validation Intern",
            url="https://spacex.com/jobs/123",
            location="Hawthorne, CA",
            matched_keywords=["silicon validation"],
        )

        # First insert should succeed
        self.assertTrue(self.db.save_job(job1))
        self.assertTrue(self.db.is_job_seen(job1.id))
        self.assertEqual(self.db.get_total_count(), 1)

        # Second insert with same job should be ignored
        self.assertFalse(self.db.save_job(job1))
        self.assertEqual(self.db.get_total_count(), 1)

        # Insert another distinct job
        job2 = JobPosting(
            company="Apple",
            title="Embedded Firmware Intern",
            url="https://jobs.apple.com/en-us/details/456",
            location="Cupertino, CA",
            matched_keywords=["embedded", "firmware"],
        )
        self.assertTrue(self.db.save_job(job2))
        self.assertEqual(self.db.get_total_count(), 2)

    def test_migrates_old_db_and_roundtrips_tier(self):
        os.remove(self.temp_path)
        with sqlite3.connect(self.temp_path) as conn:  # pre-tier schema
            conn.execute("CREATE TABLE seen_jobs (id TEXT PRIMARY KEY, company TEXT NOT NULL, title TEXT NOT NULL, "
                         "url TEXT NOT NULL, location TEXT, source TEXT, matched_keywords TEXT, terms TEXT, "
                         "sponsorship TEXT, first_seen_at TIMESTAMP, status TEXT, dedup_key TEXT, date_posted TEXT)")
            conn.execute("INSERT INTO seen_jobs (id, company, title, url, status) VALUES ('old', 'A', 'B', 'u', 'sent')")
        db = Database(self.temp_path)
        j = JobPosting("Acme", "Firmware Intern", "https://x/1", tier=1, company_type="startup")
        db.save_job(j, status="pending")
        [got] = db.pending_batch(10)
        self.assertEqual((got.id, got.tier, got.company_type), (j.id, 1, "startup"))

    def test_undigested_recent_and_mark_digested(self):
        t1 = JobPosting("Acme", "Firmware Intern", "https://x/1", tier=1)
        t2 = JobPosting("Chips", "FPGA Intern", "https://x/2", tier=2, company_type="semiconductor")
        seed = JobPosting("Old", "Embedded Intern", "https://x/3", tier=1)
        self.db.save_job(t2, status="digest")
        self.db.save_job(t1, status="pending")
        self.db.save_job(seed, status="seen")
        with self.db.get_connection() as conn:  # a 2-day-old job is out of the window
            stale = JobPosting("Stale", "Firmware Intern", "https://x/4", tier=1)
            self.db.save_job(stale, status="sent")
            conn.execute("UPDATE seen_jobs SET first_seen_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (stale.id,))
        got = self.db.undigested_recent(24)
        self.assertEqual([(g.id, g.tier, g.company_type) for g in got], [(t1.id, 1, ""), (t2.id, 2, "semiconductor")])
        self.assertEqual(self.db.pending_count(), 1)  # tier 2 never enters the instant queue
        self.db.mark_digested([g.id for g in got])
        self.assertEqual(self.db.undigested_recent(24), [])


if __name__ == "__main__":
    unittest.main()


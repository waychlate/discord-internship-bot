import os
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


if __name__ == "__main__":
    unittest.main()


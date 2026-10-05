import os
import tempfile
import unittest
from datetime import datetime, timezone

from src.dates import age_days, is_fresh
from src.db import Database
from src.filter import ECEFilter
from src.main import drip_gap
from src.models import JobPosting
from src.sources.github_markdown import GitHubMarkdownSource

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class TestAge(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(age_days("15d", NOW), 15)
        self.assertEqual(age_days("2w", NOW), 14)
        self.assertEqual(age_days("1mo", NOW), 30)
        self.assertEqual(age_days("Posted Today", NOW), 0)
        self.assertEqual(age_days("Posted Yesterday", NOW), 1)
        self.assertEqual(age_days("Posted 30+ Days Ago", NOW), 30)
        self.assertAlmostEqual(age_days("2026-10-02T12:00:00Z", NOW), 2)
        self.assertAlmostEqual(age_days("Oct 03 2026", NOW), 1.5)
        self.assertAlmostEqual(age_days("Oct 3", NOW), 1.5)
        self.assertIsNone(age_days("-", NOW))
        self.assertIsNone(age_days(None, NOW))

    def test_year_less_date_in_future_means_last_year(self):
        self.assertGreater(age_days("Dec 28", NOW), 250)

    def test_is_fresh(self):
        self.assertTrue(is_fresh("2d", 2, NOW))
        self.assertFalse(is_fresh("3d", 2, NOW))
        self.assertFalse(is_fresh("Posted 30+ Days Ago", 2, NOW))
        self.assertTrue(is_fresh(None, 2, NOW))  # undated alerts first time seen


class TestFilter(unittest.TestCase):
    cfg = {"filter": {
        "inclusion_keywords": ["fpga"], "software_keywords": ["software engineer"],
        "role_types": ["intern"], "exclusion_keywords": ["senior"],
        "always_include_regex": ["nvidia.*ignite"],
    }}

    def test_software_and_always_include(self):
        f = ECEFilter(self.cfg)
        self.assertTrue(f.evaluate(JobPosting("Acme", "Software Engineer Intern", "u"))[0])
        self.assertTrue(f.evaluate(JobPosting("NVIDIA", "2027 Ignite Program", "u"))[0])
        self.assertFalse(f.evaluate(JobPosting("Acme", "Ignite Program", "u"))[0])
        self.assertFalse(f.evaluate(JobPosting("Acme", "Senior Software Engineer Intern", "u"))[0])


class TestQueue(unittest.TestCase):
    def test_pending_roundtrip_and_migration(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(os.path.join(d, "t.db"))
            j = JobPosting("Acme", "FPGA Intern", "https://x/1", date_posted="1d", matched_keywords=["fpga"])
            db.save_job(j, status="pending")
            db.save_job(JobPosting("Old", "FPGA Intern", "https://x/2"), status="seen")
            self.assertEqual(db.pending_count(), 1)
            got = db.pending_batch(10)
            self.assertEqual([(g.id, g.matched_keywords, g.date_posted) for g in got], [(j.id, ["fpga"], "1d")])
            db.mark_sent(j.id)
            self.assertEqual(db.pending_count(), 0)
            self.assertEqual(db.pending_batch(10), [])

    def test_duplicate_across_lists(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(os.path.join(d, "t.db"))
            a = JobPosting("Affirm", "Software Engineer Intern - ML", "https://job-boards.greenhouse.io/affirm/jobs/8008645003?utm_source=Simplify")
            b = JobPosting("Affirm Inc", "Software Engineer - Machine Learning Intern", "https://boards.greenhouse.io/embed/job_app?token=8008645003&ref=x")
            db.save_job(a, status="pending")
            self.assertTrue(db.is_duplicate(b))
            kudu1 = JobPosting("Kudu", "SWE Intern (1)", "https://leidos.wd5.myworkdayjobs.com/External/job/Chantilly-VA/Software-Engineer-Intern_R-00183707")
            kudu2 = JobPosting("Kudu", "SWE Intern (2)", "https://leidos.wd5.myworkdayjobs.com/External/job/Chantilly-VA/Software-Engineer-Intern_R-00183721")
            db.save_job(kudu1, status="pending")
            self.assertFalse(db.is_duplicate(kudu2))

    def test_drip_gap(self):
        cfg = {"scraper": {"drip_window_minutes": 60, "drip_max_gap_seconds": 120, "alert_batch_size": 10}}
        self.assertEqual(drip_gap(3, cfg), 120)       # small queue: one batch, short wait
        self.assertEqual(drip_gap(300, cfg), 120)     # 30 batches in an hour
        self.assertEqual(drip_gap(1000, cfg), 36)     # 100 batches: stretched to fit the hour
        self.assertEqual(drip_gap(0, cfg), 120)


class TestParser(unittest.TestCase):
    def test_badge_link_and_pipe_in_title(self):
        md = (
            "| Company | Role | Location | Application Link | Date Posted |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| [A](https://g.co/s?q=A) | EE Intern | NY | [![Apply](https://img.shields.io/b.svg)](https://jobs/1) | Oct 03 2026 |\n"
            "| [B](https://g.co/s?q=B) | SWE Intern | Spring | Space Apps | FL | [![Apply](https://img.shields.io/b.svg)](https://jobs/2) | Oct 03 2026 |\n"
        )
        jobs = GitHubMarkdownSource("t", "u", {}).parse_markdown_tables(md)
        self.assertEqual([(j.url, j.date_posted) for j in jobs], [("https://jobs/1", "Oct 03 2026"), ("https://jobs/2", "Oct 03 2026")])
        self.assertEqual(jobs[1].title, "SWE Intern | Spring | Space Apps")


if __name__ == "__main__":
    unittest.main()

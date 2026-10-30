import os
import tempfile
import unittest
from unittest import mock

from src import digest
from src.db import Database
from src.main import run_scrape_cycle
from src.models import JobPosting

JOBS = [
    JobPosting("Acme", "Firmware Intern", "https://x/1", tier=1, company_type="startup"),
    JobPosting("Chips", "FPGA Intern", "https://x/2", tier=2),
]


def gemini_reply(text, status=200):
    res = mock.Mock(status_code=status)
    res.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return res


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        self.db.save_job(JOBS[0], status="pending")
        self.db.save_job(JOBS[1], status="digest")
        self.notifier = mock.Mock()
        self.notifier.send_text.return_value = True

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"})
    @mock.patch("src.digest.requests.post")
    def test_gemini_happy_path(self, post):
        post.return_value = gemini_reply("1. **Acme** - Firmware Intern - <https://x/1> - FreeRTOS work")
        self.assertTrue(digest.run_digest(self.db, self.notifier))
        self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "k"})
        self.assertNotIn("k", post.call_args.args[0].split("/models/")[1])  # key not in URL
        self.notifier.send_text.assert_called_once()
        self.assertIn("FreeRTOS work", self.notifier.send_text.call_args.args[0])
        self.assertEqual(self.db.undigested_recent(24), [])  # marked, won't repeat
        self.assertTrue(digest.run_digest(self.db, self.notifier))
        self.notifier.send_text.assert_called_once()  # nothing left: no second message

    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"})
    @mock.patch("src.digest.requests.post")
    def test_junk_reply_falls_back_to_plain_list(self, post):
        post.return_value = gemini_reply("I cannot help with that.")
        self.assertTrue(digest.run_digest(self.db, self.notifier))
        msg = self.notifier.send_text.call_args.args[0]
        self.assertIn("**Acme** - Firmware Intern", msg)
        self.assertIn("<https://x/2>", msg)

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("src.digest.requests.post")
    def test_no_key_no_llm_and_discord_failure_keeps_jobs(self, post):
        self.notifier.send_text.return_value = False
        self.assertFalse(digest.run_digest(self.db, self.notifier))
        post.assert_not_called()
        self.assertEqual(len(self.db.undigested_recent(24)), 2)

    def test_dry_run_prints_and_marks_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print") as p:
            self.assertTrue(digest.run_digest(self.db, self.notifier, dry_run=True))
        p.assert_called_once()
        self.notifier.send_text.assert_not_called()
        self.assertEqual(len(self.db.undigested_recent(24)), 2)

    def test_split_message(self):
        text = "\n".join(f"line {i} " + "x" * 90 for i in range(60))
        chunks = digest.split_message(text)
        self.assertTrue(all(len(c) <= 2000 for c in chunks))
        self.assertEqual("\n".join(chunks), text)


class TierRoutingTest(unittest.TestCase):
    def test_tier1_pending_tier2_digest_with_company_type(self):
        jobs = [JobPosting("A", "Firmware Intern", "https://y/1"), JobPosting("B", "FPGA Intern", "https://y/2")]
        source = mock.Mock(fetch_jobs=mock.Mock(return_value=jobs))
        source.name = "s"

        def evaluate(job):
            job.tier = 1 if "Firmware" in job.title else 2
            return True, []

        typer = mock.Mock(label=lambda c: "defense")
        with tempfile.TemporaryDirectory() as d:
            db = Database(os.path.join(d, "t.db"))
            db.save_job(JobPosting("Z", "z", "https://y/0"), status="seen")  # not a fresh DB: no quiet seed
            run_scrape_cycle([source], mock.Mock(evaluate=evaluate), db, mock.Mock(), {}, typer=typer)
            with db.get_connection() as conn:
                rows = dict(conn.execute("SELECT company, status || ':' || tier || ':' || company_type FROM seen_jobs"))
        self.assertEqual(rows["A"], "pending:1:defense")
        self.assertEqual(rows["B"], "digest:2:defense")


if __name__ == "__main__":
    unittest.main()

import unittest
from src.formatters import extract_season, format_posted_date, tier_label
from src.models import JobPosting
from src.notifier import DiscordNotifier


class TestFormatters(unittest.TestCase):
    def test_season_extraction_with_year(self):
        self.assertEqual(extract_season("Summer 2026 Hardware Intern"), "☀️ Summer 2026")
        self.assertEqual(extract_season("Embedded Firmware Intern - Fall 2025"), "🍂 Fall 2025")
        self.assertEqual(extract_season("Spring 2026 Silicon Validation Intern"), "🌱 Spring 2026")
        self.assertEqual(extract_season("Winter 2026 FPGA Co-op"), "❄️ Winter 2026")
        self.assertEqual(extract_season("Autumn 2025 Robotics Intern"), "🍂 Fall 2025")

    def test_season_extraction_without_explicit_year(self):
        self.assertEqual(extract_season("Summer Hardware Intern"), "☀️ Summer")
        self.assertEqual(extract_season("Winter Embedded Co-op"), "❄️ Winter")

    def test_season_extraction_from_source_or_terms(self):
        # Fallback to source or terms
        self.assertEqual(
            extract_season("Digital Design Intern", source_name="SimplifyJobs Summer 2026 Internships"),
            "☀️ Summer 2026",
        )
        self.assertEqual(
            extract_season("Digital Design Intern", terms="Winter 2025"),
            "❄️ Winter 2025",
        )

    def test_format_posted_date_relative(self):
        display, _ = format_posted_date("15d")
        self.assertEqual(display, "15 days ago")

        display, _ = format_posted_date("1mo")
        self.assertEqual(display, "1 month ago")

        display, _ = format_posted_date("2w")
        self.assertEqual(display, "2 weeks ago")

    def test_format_posted_date_iso(self):
        display, iso_val = format_posted_date("2026-08-15T14:20:00Z")
        self.assertIn("Aug 15, 2026", display)
        self.assertEqual(iso_val, "2026-08-15T14:20:00+00:00")

    def test_embed_shows_tier_and_company_type(self):
        job = JobPosting("Acme", "Firmware Intern", "https://x/1", tier=1, company_type="defense")
        fields = {f["name"]: f["value"] for f in DiscordNotifier({})._build_embed_payload(job)["embeds"][0]["fields"]}
        self.assertEqual(fields["🧭 Tier"], tier_label(1))
        self.assertIn("Embedded", fields["🧭 Tier"])
        self.assertEqual(fields["🏷️ Company Type"], "defense")
        self.assertNotIn("🧭 Track", fields)


if __name__ == "__main__":
    unittest.main()


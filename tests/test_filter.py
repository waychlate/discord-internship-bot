import unittest
from src.filter import ECEFilter
from src.models import JobPosting


class TestECEFilter(unittest.TestCase):
    def setUp(self):
        # Comprehensive ECE filter configuration
        config = {
            "filter": {
                "inclusion_keywords": [
                    "embedded", "firmware", "rtos", "microcontroller", "fpga",
                    "asic", "rtl", "verilog", "systemverilog", "vhdl",
                    "computer architecture", "pcb", "electrical engineer",
                    "electrical engineering", "hardware engineer",
                    "hardware engineering", "silicon validation", "robotics",
                    "power electronics"
                ],
                "role_types": ["intern", "internship", "co-op", "coop", "student"],
                "exclusion_keywords": [
                    "senior", "principal", "lead", "staff", "director", "manager",
                    "frontend", "marketing", "sales", "human resources", "social media"
                ],
            }
        }
        self.filter = ECEFilter(config)

    def test_ece_positive_matches(self):
        test_cases = [
            ("SpaceX", "Silicon Validation Intern", "Hawthorne, CA"),
            ("Apple", "Embedded Software Engineering Intern - Summer 2025", "Cupertino, CA"),
            ("NVIDIA", "FPGA Design & Emulation Intern", "Santa Clara, CA"),
            ("Qualcomm", "RTL Design Engineer Co-op", "San Diego, CA"),
            ("Tesla", "Hardware Engineering Intern (Power Electronics)", "Palo Alto, CA"),
            ("Intel", "Computer Architecture Intern", "Austin, TX"),
            ("AMD", "ASIC Verification Intern", "Boxborough, MA"),
            ("Lockheed Martin", "Electrical Engineering Intern", "Orlando, FL"),
            ("Anduril", "Robotics Controls Intern", "Costa Mesa, CA"),
            ("Verkada", "Firmware Engineering Intern", "San Mateo, CA"),
            ("Skydio", "PCB Design Intern", "San Mateo, CA"),
        ]

        for company, title, location in test_cases:
            job = JobPosting(company=company, title=title, location=location, url="https://example.com")
            is_match, tags = self.filter.evaluate(job)
            self.assertTrue(is_match, f"Expected '{title}' to match ECE filter, but it did not.")
            self.assertGreater(len(tags), 0)

    def test_ece_negative_and_exclusion_matches(self):
        test_cases = [
            # Seniority exclusions
            ("Google", "Senior Embedded Software Engineer", "Mountain View, CA"),
            ("Meta", "Principal Hardware Engineer", "Menlo Park, CA"),
            ("Amazon", "Staff FPGA Engineer", "Seattle, WA"),
            # Non-ECE fields
            ("Uber", "Frontend React Developer Intern", "San Francisco, CA"),
            ("Airbnb", "Marketing Intern", "San Francisco, CA"),
            ("Stripe", "Human Resources Intern", "Remote"),
            ("Netflix", "Social Media Intern", "Los Angeles, CA"),
        ]

        for company, title, location in test_cases:
            job = JobPosting(company=company, title=title, location=location, url="https://example.com")
            is_match, tags = self.filter.evaluate(job)
            self.assertFalse(is_match, f"Expected '{title}' to be rejected, but it matched tags: {tags}")

    def test_acronym_word_boundary_safety(self):
        false_positives = [
            ("Dispatch Health", "Logistics Operations Intern", "Denver, CO"),
            ("Alarm.com", "Sales & Marketing Intern", "Vienna, VA"),
        ]
        for company, title, location in false_positives:
            job = JobPosting(company=company, title=title, location=location, url="https://example.com")
            is_match, tags = self.filter.evaluate(job)
            self.assertFalse(is_match, f"Expected '{title}' not to falsely match acronyms, but got: {tags}")


if __name__ == "__main__":
    unittest.main()


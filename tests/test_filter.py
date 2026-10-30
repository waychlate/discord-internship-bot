import unittest
from pathlib import Path

import yaml

from src.filter import ECEFilter
from src.models import JobPosting

CONFIG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())


def job(title, location="Not specified", terms=None, company="Acme"):
    return JobPosting(company=company, title=title, url="https://example.com", location=location, terms=terms)


class TestECEFilter(unittest.TestCase):
    def setUp(self):
        self.f = ECEFilter(CONFIG)

    def check(self, posting):
        ok, tags = self.f.evaluate(posting)
        return ok, posting.tier, tags

    def test_tier1_embedded_firmware_title(self):
        for title in [
            "Embedded Software Engineering Intern",
            "Firmware Engineering Intern",
            "RTOS Intern",
            "Device Drivers Co-op",
            "Bare Metal Software Intern",
            "STM32 Firmware Intern",
            "Low-Level Systems Intern",
        ]:
            ok, tier, tags = self.check(job(title, "Austin, TX"))
            self.assertTrue(ok, title)
            self.assertEqual(tier, 1, title)
            self.assertTrue(tags)

    def test_tier2_hardware(self):
        for title in [
            "FPGA Design & Emulation Intern",
            "RTL Design Engineer Co-op",
            "ASIC Verification Intern",
            "Hardware Engineering Intern (Power Electronics)",
            "Electrical Engineering Intern",
            "PCB Design Intern",
            "Analog Front End Intern",
            "RF Systems Intern",
            "Robotics Controls Intern",
            "DSP Intern",
            "Silicon Validation Intern",
            "Computer Architecture Intern",
        ]:
            ok, tier, _ = self.check(job(title, "San Diego, CA"))
            self.assertTrue(ok, title)
            self.assertEqual(tier, 2, title)

    def test_tier1_beats_tier2_and_is_title_only(self):
        self.assertEqual(self.check(job("Embedded FPGA Intern"))[1], 1)
        # "embedded" only in terms/company -> not tier 1
        ok, tier, _ = self.check(job("Hardware Intern", company="Embedded Corp"))
        self.assertEqual((ok, tier), (True, 2))

    def test_swe_and_non_ece_rejected(self):
        for title in [
            "Software Engineer Intern",
            "Backend Engineering Intern",
            "Full Stack Developer Intern",
            "DevOps Intern",
            "Frontend React Developer Intern",
            "Data Science Intern",
            "Marketing Intern",
            "Logistics Operations Intern",
        ]:
            ok, tier, tags = self.check(job(title))
            self.assertFalse(ok, f"{title} matched {tags}")
            self.assertEqual(tier, 0)

    def test_exclusions_and_role(self):
        for title in [
            "Senior Embedded Software Engineer",
            "Staff FPGA Engineer",
            "PhD Firmware Intern",
            "Firmware Engineer",  # not an internship
        ]:
            self.assertFalse(self.check(job(title))[0], title)

    def test_season(self):
        accept = [
            ("Firmware Intern", None),
            ("Firmware Intern - Summer 2027", None),
            ("Firmware Intern", "Summer 2027"),
            ("Firmware Intern", "Fall 2027"),
            ("Firmware Intern", "Spring 2027, Summer 2027"),
            ("Firmware Intern 2027", None),
            ("Summer Firmware Intern", None),
        ]
        reject = [
            ("Firmware Intern - Summer 2026", None),
            ("Firmware Intern", "Spring 2027"),
            ("Firmware Intern", "Winter 2027"),
            ("Winter Firmware Co-op", None),
            ("Firmware Intern 2028", None),
            ("Firmware Intern", "Summer 2028"),
        ]
        for title, terms in accept:
            self.assertTrue(self.check(job(title, terms=terms))[0], (title, terms))
        for title, terms in reject:
            self.assertFalse(self.check(job(title, terms=terms))[0], (title, terms))

    def test_us_only(self):
        for loc in ["Austin, TX", "Remote", "Not specified", "", "New London, CT", "Remote - US"]:
            self.assertTrue(self.check(job("Firmware Intern", loc))[0], loc)
        for loc in ["Toronto, ON, Canada", "Bangalore, India", "Cambridge, UK", "Remote - EMEA", "Munich, Germany"]:
            self.assertFalse(self.check(job("Firmware Intern", loc))[0], loc)

    def test_always_include_is_tier1(self):
        ok, tier, _ = self.check(job("2027 Ignite Program", company="NVIDIA"))
        self.assertEqual((ok, tier), (True, 1))
        self.assertFalse(self.check(job("Ignite Program"))[0])


if __name__ == "__main__":
    unittest.main()

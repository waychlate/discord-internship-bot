import unittest
from src.sources.github_markdown import GitHubMarkdownSource


class TestMarkdownParser(unittest.TestCase):
    def test_markdown_table_parsing(self):
        sample_markdown = """
# Summer 2026 Tech Internships

| Company | Role | Location | Application/Link | Date Posted |
| :--- | :--- | :--- | :--- | :--- |
| **[NVIDIA](https://nvidia.com)** | FPGA & Emulation Intern | Santa Clara, CA | [Apply](https://nvidia.wd5.myworkdayjobs.com/job/1) | May 1 |
| [Apple](https://apple.com) | Hardware Systems Intern | Cupertino, CA | <a href="https://jobs.apple.com/2">Apply Here</a> | May 2 |
| SpaceX | Starlink Firmware Intern | Redmond, WA | https://boards.greenhouse.io/spacex/jobs/3 | May 3 |
| Unrelated | Senior Manager | Remote | [Link](https://example.com) | May 4 |
"""

        source = GitHubMarkdownSource("Test Source", "https://example.com/readme.md", {})
        jobs = source.parse_markdown_tables(sample_markdown)

        self.assertEqual(len(jobs), 4)
        
        self.assertEqual(jobs[0].company, "NVIDIA")
        self.assertEqual(jobs[0].title, "FPGA & Emulation Intern")
        self.assertEqual(jobs[0].url, "https://nvidia.wd5.myworkdayjobs.com/job/1")
        self.assertEqual(jobs[0].location, "Santa Clara, CA")

        self.assertEqual(jobs[1].company, "Apple")
        self.assertEqual(jobs[1].title, "Hardware Systems Intern")
        self.assertEqual(jobs[1].url, "https://jobs.apple.com/2")

        self.assertEqual(jobs[2].company, "SpaceX")
        self.assertEqual(jobs[2].title, "Starlink Firmware Intern")
        self.assertEqual(jobs[2].url, "https://boards.greenhouse.io/spacex/jobs/3")


if __name__ == "__main__":
    unittest.main()


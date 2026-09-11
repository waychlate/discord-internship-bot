import unittest
from src.models import JobPosting


class TestJobModels(unittest.TestCase):
    def test_job_id_deterministic_hash(self):
        job1 = JobPosting(
            company="NVIDIA",
            title="Hardware Intern",
            url="https://nvidia.com/jobs/1?source=referral",
        )
        job2 = JobPosting(
            company="nvidia",
            title="hardware intern",
            url="https://nvidia.com/jobs/1",
        )
        self.assertEqual(job1.id, job2.id)

    def test_distinct_jobs_have_different_ids(self):
        job1 = JobPosting(
            company="NVIDIA",
            title="Hardware Intern",
            url="https://nvidia.com/jobs/1",
        )
        job2 = JobPosting(
            company="NVIDIA",
            title="Software Intern",
            url="https://nvidia.com/jobs/2",
        )
        self.assertNotEqual(job1.id, job2.id)


if __name__ == "__main__":
    unittest.main()


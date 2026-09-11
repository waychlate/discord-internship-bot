import logging
from typing import Dict, List
import requests

from src.models import JobPosting
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class ATSBoardSource(BaseSource):
    """Scrapes direct public ATS API feeds from Greenhouse and Lever."""

    def __init__(self, name: str, config: Dict):
        super().__init__(name, config)
        self.timeout = config.get("scraper", {}).get("timeout_seconds", 15)
        self.user_agent = config.get("scraper", {}).get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        sources_cfg = config.get("sources", {})
        self.greenhouse_boards = sources_cfg.get("greenhouse_boards", [])
        self.lever_boards = sources_cfg.get("lever_boards", [])

    def fetch_jobs(self) -> List[JobPosting]:
        postings: List[JobPosting] = []

        # 1. Fetch Greenhouse boards
        for board in self.greenhouse_boards:
            try:
                board_jobs = self._fetch_greenhouse(board)
                postings.extend(board_jobs)
            except Exception as e:
                logger.warning(f"Error fetching Greenhouse board {board}: {e}")

        # 2. Fetch Lever boards
        for board in self.lever_boards:
            try:
                board_jobs = self._fetch_lever(board)
                postings.extend(board_jobs)
            except Exception as e:
                logger.warning(f"Error fetching Lever board {board}: {e}")

        return postings

    def _fetch_greenhouse(self, board_token: str) -> List[JobPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
        headers = {"User-Agent": self.user_agent}
        res = requests.get(url, headers=headers, timeout=self.timeout)
        if res.status_code != 200:
            return []

        data = res.json()
        jobs = data.get("jobs", [])
        results: List[JobPosting] = []

        company_name = board_token.capitalize()
        for j in jobs:
            title = j.get("title", "")
            job_url = j.get("absolute_url", "")
            location = j.get("location", {}).get("name", "Not specified")
            updated_at = j.get("updated_at", "")

            if title and job_url:
                results.append(
                    JobPosting(
                        company=company_name,
                        title=title,
                        url=job_url,
                        location=location,
                        source=f"Greenhouse ({company_name})",
                        date_posted=updated_at,
                    )
                )
        return results

    def _fetch_lever(self, board_token: str) -> List[JobPosting]:
        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        headers = {"User-Agent": self.user_agent}
        res = requests.get(url, headers=headers, timeout=self.timeout)
        if res.status_code != 200:
            return []

        data = res.json()
        results: List[JobPosting] = []
        company_name = board_token.capitalize()

        for j in data:
            title = j.get("text", "")
            job_url = j.get("hostedUrl", "") or j.get("applyUrl", "")
            categories = j.get("categories", {})
            location = categories.get("location", "Not specified")
            commitment = categories.get("commitment", "")

            if title and job_url:
                results.append(
                    JobPosting(
                        company=company_name,
                        title=title,
                        url=job_url,
                        location=location,
                        source=f"Lever ({company_name})",
                        terms=commitment or None,
                    )
                )
        return results


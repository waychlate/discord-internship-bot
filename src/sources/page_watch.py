import hashlib
import json
import logging
import os
import re
from typing import Dict, List
import requests
from bs4 import BeautifulSoup

from src.models import JobPosting
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class PageWatchSource(BaseSource):
    """Alerts when the text on a page that mentions `keyword` changes (e.g. NVIDIA Ignite opening).

    The first run only records a baseline. The alert's URL carries the content hash, so the
    normal DB dedup means each distinct change alerts once.
    """

    def __init__(self, watch: Dict, config: Dict):
        super().__init__(watch["name"], config)
        self.url = watch["url"]
        self.keyword = watch["keyword"].lower()
        self.company = watch.get("company", watch["name"])
        self.state_path = os.path.join(
            os.path.dirname(config.get("scraper", {}).get("db_path", "data/jobs.db")) or ".", "page_watch.json"
        )
        self.timeout = config.get("scraper", {}).get("timeout_seconds", 15)
        self.user_agent = config.get("scraper", {}).get("user_agent", "Mozilla/5.0")

    def _relevant_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        # Text blocks mentioning the keyword; the rest of the page churns (carousels, nav).
        blocks = {
            re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            for el in soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "a", "span"])
            if self.keyword in el.get_text(" ", strip=True).lower()
        }
        return "\n".join(sorted(blocks))

    def fetch_jobs(self) -> List[JobPosting]:
        res = requests.get(self.url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
        res.raise_for_status()
        text = self._relevant_text(res.text)
        if not text:
            return []
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]

        try:
            with open(self.state_path) as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        if state.get(self.url) == digest:
            return []
        first_run = self.url not in state
        state[self.url] = digest
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(state, f)
        if first_run:
            logger.info(f"{self.name}: recorded baseline for {self.url}")
            return []

        return [
            JobPosting(
                company=self.company,
                title=f"{self.name}: page updated, check if applications are open",
                url=f"{self.url}#{digest}",
                source="Page Watcher",
                matched_keywords=[self.keyword],
                pre_approved=True,
            )
        ]

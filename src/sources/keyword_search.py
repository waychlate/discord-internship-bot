import logging
import os
from typing import Dict, List
import requests

from src.models import JobPosting
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class _SearchSource(BaseSource):
    """Keyword-search job APIs. Queries come from config `keyword_search.queries`; the usual
    filter (keywords + intern + age) still decides what gets alerted."""

    def __init__(self, name: str, config: Dict):
        super().__init__(name, config)
        self.timeout = config.get("scraper", {}).get("timeout_seconds", 15)
        ks = config.get("keyword_search", {})
        self.queries = ks.get("queries", [])
        self.max_age_days = max(1, int(config.get("scraper", {}).get("max_age_days", 2)))

    def fetch_jobs(self) -> List[JobPosting]:
        postings: List[JobPosting] = []
        for q in self.queries:
            try:
                postings.extend(self._search(q))
            except Exception as e:
                logger.warning(f"{self.name} search '{q}' failed: {e}")
        return postings


class AdzunaSource(_SearchSource):
    """https://developer.adzuna.com (free key). Needs ADZUNA_APP_ID / ADZUNA_APP_KEY."""

    def __init__(self, config: Dict):
        super().__init__("Adzuna", config)
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.app_key = os.getenv("ADZUNA_APP_KEY", "")

    def enabled(self) -> bool:
        return bool(self.app_id and self.app_key and self.queries)

    def _search(self, query: str) -> List[JobPosting]:
        res = requests.get(
            "https://api.adzuna.com/v1/api/jobs/us/search/1",
            params={
                "app_id": self.app_id, "app_key": self.app_key, "what": query,
                "max_days_old": self.max_age_days, "results_per_page": 50, "sort_by": "date",
            },
            timeout=self.timeout,
        )
        res.raise_for_status()
        return [
            JobPosting(
                company=(j.get("company") or {}).get("display_name", "Unknown"),
                title=j["title"],
                url=j["redirect_url"],
                location=(j.get("location") or {}).get("display_name", "Not specified"),
                source="Adzuna",
                date_posted=j.get("created"),
            )
            for j in res.json().get("results", [])
            if j.get("title") and j.get("redirect_url")
        ]


class USAJobsSource(_SearchSource):
    """https://developer.usajobs.gov (free key). Needs USAJOBS_API_KEY and USAJOBS_EMAIL."""

    def __init__(self, config: Dict):
        super().__init__("USAJobs", config)
        self.api_key = os.getenv("USAJOBS_API_KEY", "")
        self.email = os.getenv("USAJOBS_EMAIL", "")

    def enabled(self) -> bool:
        return bool(self.api_key and self.email and self.queries)

    def _search(self, query: str) -> List[JobPosting]:
        res = requests.get(
            "https://data.usajobs.gov/api/search",
            params={"Keyword": query, "DatePosted": self.max_age_days, "ResultsPerPage": 50},
            headers={"Host": "data.usajobs.gov", "User-Agent": self.email, "Authorization-Key": self.api_key},
            timeout=self.timeout,
        )
        res.raise_for_status()
        out = []
        for item in res.json().get("SearchResult", {}).get("SearchResultItems", []):
            d = item.get("MatchedObjectDescriptor", {})
            if d.get("PositionTitle") and d.get("PositionURI"):
                out.append(
                    JobPosting(
                        company=d.get("OrganizationName", "US Government"),
                        title=d["PositionTitle"],
                        url=d["PositionURI"],
                        location=d.get("PositionLocationDisplay", "Not specified"),
                        source="USAJobs",
                        date_posted=d.get("PublicationStartDate"),
                    )
                )
        return out

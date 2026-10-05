import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List
import requests

from src.dates import age_days, days_ago_iso
from src.models import JobPosting
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

WORKDAY_PAGE = 20  # Workday's CXS API rejects larger pages
WORKDAY_MAX_PAGES = 25  # ponytail: 500 jobs/board cap; Workday doesn't sort by date, raise if a board is bigger


class ATSBoardSource(BaseSource):
    """Public ATS feeds (Greenhouse, Lever, Ashby, SmartRecruiters, Workday) for the `companies:` list.

    Each company is `{name, ats, slug}`; Workday slugs are `tenant/site` plus a `host`.
    """

    def __init__(self, name: str, config: Dict):
        super().__init__(name, config)
        scraper_cfg = config.get("scraper", {})
        self.timeout = scraper_cfg.get("timeout_seconds", 15)
        self.headers = {
            "User-Agent": scraper_cfg.get(
                "user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        }
        self.companies = config.get("sources", {}).get("companies", [])
        self._fetchers = {
            "greenhouse": self._greenhouse,
            "lever": self._lever,
            "ashby": self._ashby,
            "smartrecruiters": self._smartrecruiters,
            "workday": self._workday,
        }

    def _fetch_company(self, c: Dict) -> List[JobPosting]:
        fetch = self._fetchers.get(c.get("ats"))
        if not fetch:
            logger.warning(f"Unsupported ATS '{c.get('ats')}' for {c.get('name')}")
            return []
        try:
            return fetch(c)
        except Exception as e:
            logger.warning(f"Error fetching {c['ats']} board for {c.get('name')}: {e}")
            return []

    def fetch_jobs(self) -> List[JobPosting]:
        # Boards are independent and slow (Workday pages through hundreds of jobs), so fetch in parallel
        with ThreadPoolExecutor(max_workers=8) as pool:
            return [j for jobs in pool.map(self._fetch_company, self.companies) for j in jobs]

    def _job(self, c: Dict, title, url, location, date_posted, terms=None) -> JobPosting:
        return JobPosting(
            company=c["name"],
            title=title,
            url=url,
            location=location or "Not specified",
            source=f"{c['ats'].capitalize()} ({c['name']})",
            date_posted=date_posted,
            terms=terms,
        )

    def _get_json(self, url: str):
        res = requests.get(url, headers=self.headers, timeout=self.timeout)
        res.raise_for_status()
        return res.json()

    def _greenhouse(self, c: Dict) -> List[JobPosting]:
        data = self._get_json(f"https://boards-api.greenhouse.io/v1/boards/{c['slug']}/jobs")
        return [
            # first_published, not updated_at: recruiters touch old reqs and bump updated_at
            self._job(
                c, j["title"], j["absolute_url"], (j.get("location") or {}).get("name"),
                j.get("first_published") or None,
            )
            for j in data.get("jobs", [])
            if j.get("title") and j.get("absolute_url")
        ]

    def _lever(self, c: Dict) -> List[JobPosting]:
        results = []
        for j in self._get_json(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json"):
            url = j.get("hostedUrl") or j.get("applyUrl")
            if not (j.get("text") and url):
                continue
            created = j.get("createdAt")
            date_posted = (
                datetime.fromtimestamp(created / 1000.0, timezone.utc).isoformat() if created else None
            )
            cats = j.get("categories") or {}
            results.append(
                self._job(c, j["text"], url, cats.get("location"), date_posted, terms=cats.get("commitment"))
            )
        return results

    def _ashby(self, c: Dict) -> List[JobPosting]:
        data = self._get_json(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}")
        return [
            self._job(c, j["title"], j["jobUrl"], j.get("location"), j.get("publishedAt"))
            for j in data.get("jobs", [])
            if j.get("title") and j.get("jobUrl") and j.get("isListed", True)
        ]

    def _smartrecruiters(self, c: Dict) -> List[JobPosting]:
        results, offset = [], 0
        while True:
            data = self._get_json(
                f"https://api.smartrecruiters.com/v1/companies/{c['slug']}/postings?limit=100&offset={offset}"
            )
            for j in data.get("content", []):
                loc = j.get("location") or {}
                location = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
                results.append(
                    self._job(
                        c, j["name"], f"https://jobs.smartrecruiters.com/{c['slug']}/{j['id']}",
                        location, j.get("releasedDate"),
                    )
                )
            offset += 100
            if offset >= data.get("totalFound", 0):
                return results

    def _workday(self, c: Dict) -> List[JobPosting]:
        tenant, site = c["slug"].split("/", 1)
        host = c["host"].rstrip("/")
        api = f"{host}/wday/cxs/{tenant}/{site}/jobs"
        results, total = [], 0
        for page in range(WORKDAY_MAX_PAGES):
            res = requests.post(
                api,
                json={"appliedFacets": {}, "limit": WORKDAY_PAGE, "offset": page * WORKDAY_PAGE, "searchText": "intern"},
                headers=self.headers,
                timeout=self.timeout,
            )
            res.raise_for_status()
            data = res.json()
            total = total or data.get("total", 0)  # only sent on the first page
            for j in data.get("jobPostings", []):
                if not (j.get("title") and j.get("externalPath")):
                    continue
                # "Posted 3 Days Ago" -> ISO date; "30+" lands on 30 days, which the age cap rejects
                age = age_days(j.get("postedOn"))
                results.append(
                    self._job(
                        c, j["title"], f"{host}/{site}{j['externalPath']}", j.get("locationsText"),
                        days_ago_iso(age) if age is not None else None,
                    )
                )
            if (page + 1) * WORKDAY_PAGE >= total:
                break
        return results

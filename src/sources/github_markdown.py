import logging
import re
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from src.models import JobPosting
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class GitHubMarkdownSource(BaseSource):
    def __init__(self, name: str, repo_url: str, config: Dict):
        super().__init__(name, config)
        self.repo_url = repo_url
        self.timeout = config.get("scraper", {}).get("timeout_seconds", 15)
        self.user_agent = config.get("scraper", {}).get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

    def fetch_jobs(self) -> List[JobPosting]:
        headers = {"User-Agent": self.user_agent}
        try:
            logger.info(f"Fetching GitHub content from {self.name} ({self.repo_url})...")
            response = requests.get(self.repo_url, headers=headers, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch {self.name}: status code {response.status_code}"
                )
                return []
            
            content = response.text
            # Try HTML table parsing first (used by SimplifyJobs & PittCSC)
            html_jobs = self.parse_html_tables(content)
            if html_jobs:
                logger.info(f"Parsed {len(html_jobs)} jobs via HTML table parser from {self.name}")
                return html_jobs

            # Fallback to Markdown pipe tables
            md_jobs = self.parse_markdown_tables(content)
            logger.info(f"Parsed {len(md_jobs)} jobs via Markdown pipe parser from {self.name}")
            return md_jobs
        except Exception as e:
            logger.error(f"Error fetching from {self.name}: {e}")
            return []

    def parse_html_tables(self, content: str) -> List[JobPosting]:
        """Parses HTML tables (e.g. <table><tr><td>...</td></tr></table>) found in READMEs."""
        if "<table" not in content.lower() or "<tr" not in content.lower():
            return []

        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return []

        postings: List[JobPosting] = []
        last_company = ""

        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue

            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) < 3:
                    continue

                # Skip table headers
                if row.find("th"):
                    continue

                # Col 0: Company, Col 1: Role, Col 2: Location, Col 3: Link, Col 4: Date/Age
                col_texts = [c.get_text(separator=" ").strip() for c in cols]
                raw_company = col_texts[0]

                # Check for sub-role arrow '↳'
                if "↳" in raw_company or not raw_company:
                    company = last_company
                else:
                    # Clean company name
                    company_a = cols[0].find("a")
                    company = company_a.get_text().strip() if company_a else raw_company
                    company = re.sub(r"[\*\_`]", "", company).strip()
                    if company:
                        last_company = company

                if not company:
                    continue

                title = col_texts[1] if len(col_texts) > 1 else ""
                title = re.sub(r"[\*\_`]", "", title).strip()
                # Clean up decorative emojis e.g. 🎓 🔒
                title = re.sub(r"[🎓🔒🔥⚡]", "", title).strip()

                location = col_texts[2] if len(col_texts) > 2 else "Not specified"
                # Clean up <details><summary> tags if present
                location = location.replace("\n", " ").strip()

                # Extract application link from col 3 or col 1
                job_url = None
                link_col = cols[3] if len(cols) > 3 else cols[1]
                links = link_col.find_all("a")
                for a in links:
                    href = a.get("href", "")
                    # Prioritize direct ATS or company links over aggregator metadata links
                    if href and not href.startswith("#") and "simplify.jobs/p/" not in href:
                        job_url = href
                        break

                if not job_url and links:
                    job_url = links[0].get("href", "")

                if company and title and job_url:
                    date_posted = col_texts[4] if len(col_texts) > 4 else None
                    postings.append(
                        JobPosting(
                            company=company,
                            title=title,
                            url=job_url,
                            location=location,
                            source=self.name,
                            date_posted=date_posted,
                        )
                    )

        return postings

    def parse_markdown_tables(self, markdown_text: str) -> List[JobPosting]:
        postings: List[JobPosting] = []
        lines = markdown_text.splitlines()
        
        in_table = False
        headers: List[str] = []
        header_map: Dict[str, int] = {}
        last_company = ""

        for line in lines:
            line_str = line.strip()
            if not line_str.startswith("|") or not line_str.endswith("|"):
                in_table = False
                headers = []
                header_map = {}
                continue

            columns = [c.strip() for c in line_str.split("|")[1:-1]]
            if not columns:
                continue

            if all(re.match(r"^:?-+:?$", c) for c in columns if c):
                in_table = True
                continue

            if not in_table:
                headers = [c.lower() for c in columns]
                header_map = {}
                for idx, h in enumerate(headers):
                    if "company" in h or "organization" in h:
                        header_map["company"] = idx
                    elif "role" in h or "title" in h or "position" in h:
                        header_map["title"] = idx
                    elif "location" in h:
                        header_map["location"] = idx
                    elif "application" in h or "link" in h or "apply" in h:
                        header_map["link"] = idx
                    elif "date" in h or "age" in h:
                        header_map["date"] = idx
                    elif "terms" in h or "season" in h:
                        header_map["terms"] = idx
                continue

            if in_table and "company" in header_map and "title" in header_map:
                try:
                    company_raw = columns[header_map["company"]] if header_map["company"] < len(columns) else ""
                    title_raw = columns[header_map["title"]] if header_map["title"] < len(columns) else ""
                    loc_raw = columns[header_map["location"]] if "location" in header_map and header_map["location"] < len(columns) else ""
                    link_raw = columns[header_map["link"]] if "link" in header_map and header_map["link"] < len(columns) else ""
                    date_raw = columns[header_map["date"]] if "date" in header_map and header_map["date"] < len(columns) else ""
                    terms_raw = columns[header_map["terms"]] if "terms" in header_map and header_map["terms"] < len(columns) else ""

                    if "↳" in company_raw or not company_raw:
                        company = last_company
                    else:
                        company, _ = self._extract_text_and_link(company_raw)
                        if company:
                            last_company = company

                    title, title_link = self._extract_text_and_link(title_raw)
                    location, _ = self._extract_text_and_link(loc_raw)
                    _, direct_link = self._extract_text_and_link(link_raw)

                    job_url = direct_link or title_link
                    if not job_url:
                        urls = re.findall(r'https?://[^\s<>"\)\]]+', line_str)
                        if urls:
                            job_url = urls[0]

                    if company and title and job_url:
                        postings.append(
                            JobPosting(
                                company=company,
                                title=title,
                                url=job_url,
                                location=location or "Not specified",
                                source=self.name,
                                date_posted=date_raw or None,
                                terms=terms_raw or None,
                            )
                        )
                except Exception as ex:
                    logger.debug(f"Row parse skip: {ex}")
                    continue

        return postings

    def _extract_text_and_link(self, raw_str: str) -> (str, Optional[str]):
        if not raw_str:
            return "", None

        link = None
        if "<" in raw_str and ">" in raw_str:
            soup = BeautifulSoup(raw_str, "html.parser")
            a_tag = soup.find("a")
            if a_tag and a_tag.get("href"):
                link = a_tag["href"]
            text = soup.get_text().strip()
        else:
            text = raw_str

        md_match = re.search(r"\[([^\]]+)\]\((https?://[^\)]+)\)", raw_str)
        if md_match:
            text = md_match.group(1).strip()
            link = md_match.group(2).strip()

        text = re.sub(r"[\*\_`]", "", text).strip()
        return text, link


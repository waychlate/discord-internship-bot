import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobPosting:
    company: str
    title: str
    url: str
    location: str = "Not specified"
    source: str = "Unknown"
    date_posted: Optional[str] = None
    matched_keywords: List[str] = field(default_factory=list)
    terms: Optional[str] = None  # e.g. "Summer 2025", "Fall 2025"
    sponsorship: Optional[str] = None
    pre_approved: bool = False  # skip keyword filter (e.g. page-watcher alerts)
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def id(self) -> str:
        """Generate a deterministic unique hash for deduplication."""
        # Normalize fields for consistent hashing
        clean_company = self.company.strip().lower()
        clean_title = self.title.strip().lower()
        clean_url = self.url.strip().split("?")[0].rstrip("/").lower()
        
        # Use URL if available, otherwise company + title
        unique_payload = f"{clean_company}:{clean_title}:{clean_url}"
        return hashlib.sha256(unique_payload.encode("utf-8")).hexdigest()[:16]


    @property
    def dedup_key(self) -> str:
        """Same posting seen on different lists shares an ATS job id in its URL; use that when present."""
        url = self.url.strip()
        for pattern in _JOB_ID_PATTERNS:
            m = pattern.search(url)
            if m:
                return "id:" + m.group(1).lower()
        return "url:" + url.split("?")[0].split("#")[0].rstrip("/").lower()


# First match wins. Ids are specific enough (UUID, 7+ digits, req numbers) to be unique without the company.
_JOB_ID_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"[?&](?:gh_jid|token|jk)=(\w{6,})",
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",  # Ashby / Lever
        r"/jobs/view/(\d{7,})",  # LinkedIn
        r"/jobs?/(\d{7,})",  # Greenhouse, iCIMS, Amazon, workatastartup
        r"[_/-]((?:JR|REQ|R)[-_]?\d{4,})(?:[-_/?]|$)",  # Workday requisitions
    )
]

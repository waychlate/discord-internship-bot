import hashlib
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


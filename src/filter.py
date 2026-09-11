import re
from typing import Dict, List, Optional, Tuple
from src.models import JobPosting


class ECEFilter:
    def __init__(self, config: Dict):
        filter_cfg = config.get("filter", {})
        self.inclusion_keywords = [
            k.lower().strip() for k in filter_cfg.get("inclusion_keywords", [])
        ]
        self.role_types = [
            r.lower().strip() for r in filter_cfg.get("role_types", ["intern", "co-op", "coop"])
        ]
        self.exclusion_keywords = [
            e.lower().strip() for e in filter_cfg.get("exclusion_keywords", [])
        ]
        
        # Precompile regex patterns for boundary-sensitive terms (e.g. short acronyms)
        self._inclusion_patterns = [self._build_pattern(k) for k in self.inclusion_keywords]
        self._role_patterns = [self._build_pattern(r) for r in self.role_types]
        self._exclusion_patterns = [self._build_pattern(e) for e in self.exclusion_keywords]

    def _build_pattern(self, keyword: str) -> re.Pattern:
        """Build regex pattern respecting word boundaries, especially for short acronyms."""
        # Escape special regex chars
        escaped = re.escape(keyword)
        # Handle cases like c/c++ or c++
        if keyword in ["c++", "c/c++"]:
            return re.compile(r"(?:\b|\s)" + re.escape(keyword) + r"(?:\b|\s|[,\.;])", re.IGNORECASE)
        return re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)

    def evaluate(self, posting: JobPosting) -> Tuple[bool, List[str]]:
        """
        Evaluate if a job posting qualifies as an ECE internship.
        Returns (is_match, list_of_matched_keywords).
        """
        search_text = f"{posting.title} {posting.company} {posting.location or ''} {posting.terms or ''}"

        # 1. Check Exclusion Keywords first
        for i, pattern in enumerate(self._exclusion_patterns):
            if pattern.search(search_text):
                # If excluded, reject immediately
                return False, []

        # 2. Check Role Type (internship / co-op)
        # If the source explicitly labeled terms (like Summer 2025 Intern), treat as satisfied.
        role_matched = False
        if posting.terms and any(r in posting.terms.lower() for r in ["intern", "co-op", "coop", "student"]):
            role_matched = True
        else:
            for pattern in self._role_patterns:
                if pattern.search(search_text):
                    role_matched = True
                    break

        if not role_matched:
            return False, []

        # 3. Check ECE Inclusion Keywords
        matched_tags: List[str] = []
        for kw, pattern in zip(self.inclusion_keywords, self._inclusion_patterns):
            if pattern.search(search_text):
                matched_tags.append(kw)

        if matched_tags:
            posting.matched_keywords = matched_tags
            return True, matched_tags

        return False, []


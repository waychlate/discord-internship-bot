import re
from typing import Dict, List, Tuple
from src.models import JobPosting

_SEASON_YEAR = re.compile(r"\b(summer|winter|spring|fall|autumn)\s*[-/]?\s*(20\d\d)\b", re.IGNORECASE)
_SEASON = re.compile(r"\b(summer|winter|spring|fall|autumn)\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")


def _lower(items) -> List[str]:
    return [s.lower().strip() for s in items]


class ECEFilter:
    def __init__(self, config: Dict):
        cfg = config.get("filter", {})
        self.tier1_keywords = _lower(cfg.get("tier1_keywords", []))
        self.tier2_keywords = _lower(cfg.get("tier2_keywords", []))
        # "company title" regexes that skip the keyword/role checks (e.g. NVIDIA Ignite)
        self._always_include = [re.compile(r, re.IGNORECASE) for r in cfg.get("always_include_regex", [])]
        self.accepted_seasons = {
            s.replace("autumn", "fall") for s in _lower(cfg.get("accepted_seasons", ["summer 2027", "fall 2027"]))
        }
        self._accepted_names = {s.split()[0] for s in self.accepted_seasons}
        self._accepted_years = {s.split()[-1] for s in self.accepted_seasons}

        self._tier1 = [(k, self._build_pattern(k)) for k in self.tier1_keywords]
        self._tier2 = [(k, self._build_pattern(k)) for k in self.tier2_keywords]
        self._role_patterns = [self._build_pattern(r) for r in _lower(cfg.get("role_types", ["intern", "co-op", "coop"]))]
        self._exclusion_patterns = [self._build_pattern(e) for e in _lower(cfg.get("exclusion_keywords", []))]
        self._non_us_patterns = [self._build_pattern(m) for m in _lower(cfg.get("non_us_markers", []))]

    def _build_pattern(self, keyword: str) -> re.Pattern:
        """Whole-word match (optional plural 's'), so short acronyms like 'rf' or 'bsp' don't hit inside words."""
        return re.compile(r"(?<!\w)" + re.escape(keyword) + r"s?(?!\w)", re.IGNORECASE)

    def _season_ok(self, posting: JobPosting) -> bool:
        """Explicit 'Season YYYY' must be accepted; otherwise any bare season/year must not conflict."""
        text = f"{posting.terms or ''} {posting.title}"
        pairs = [(s.lower().replace("autumn", "fall"), y) for s, y in _SEASON_YEAR.findall(text)]
        if pairs:
            return any(f"{s} {y}" in self.accepted_seasons for s, y in pairs)
        seasons = {s.lower().replace("autumn", "fall") for s in _SEASON.findall(text)}
        years = set(_YEAR.findall(text))
        return seasons <= self._accepted_names and years <= self._accepted_years

    def evaluate(self, posting: JobPosting) -> Tuple[bool, List[str]]:
        """
        Evaluate if a posting is a US, Summer/Fall 2027, ECE internship.
        Sets posting.tier (1 = embedded/firmware, 2 = other hardware, 0 = no match).
        Returns (is_match, list_of_matched_keywords).
        """
        posting.tier = 0
        search_text = f"{posting.title} {posting.company} {posting.location or ''} {posting.terms or ''}"

        if any(p.search(f"{posting.company} {posting.title}") for p in self._always_include):
            posting.tier = 1
            posting.matched_keywords = posting.matched_keywords or ["priority program"]
            return True, posting.matched_keywords

        if any(p.search(search_text) for p in self._exclusion_patterns):
            return False, []

        # Role type: source-labeled terms (e.g. "Summer 2027 Intern") count as satisfied.
        terms = (posting.terms or "").lower()
        if not (any(r in terms for r in ("intern", "co-op", "coop", "student"))
                or any(p.search(search_text) for p in self._role_patterns)):
            return False, []

        if not self._season_ok(posting):
            return False, []

        # ponytail: any non-US marker rejects, so a multi-city "San Jose; Toronto" posting is dropped too.
        if any(p.search(posting.location or "") for p in self._non_us_patterns):
            return False, []

        # Tier 1 is title-only to avoid noise; tier 2 may match anywhere in the search text.
        tags = [k for k, p in self._tier1 if p.search(posting.title)]
        if tags:
            posting.tier = 1
        else:
            tags = [k for k, p in self._tier2 if p.search(f"{posting.title} {posting.location or ''} {posting.terms or ''}")]
            if not tags:
                return False, []
            posting.tier = 2

        posting.matched_keywords = tags
        return True, tags

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

_UNIT_DAYS = {"min": 1 / 1440, "m": 1 / 1440, "h": 1 / 24, "d": 1, "w": 7, "mo": 30, "y": 365}


def age_days(raw: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Age of a posting in days from any date string we scrape, or None if unknown/unparseable.

    Handles ISO timestamps, "15d"/"2w"/"1mo" (GitHub lists), "Posted 3 Days Ago" /
    "Posted 30+ Days Ago" / "Posted Today" (Workday), "Oct 3", "2026-10-03", "10/03/2026".
    """
    if not raw:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    now = now or datetime.now(timezone.utc)

    if "today" in s or "just now" in s:
        return 0.0
    if "yesterday" in s:
        return 1.0
    m = re.search(r"(\d+)\s*\+?\s*days?\s*ago", s)
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+)\s*(min|mo|[mhdwy])", s)
    if m:
        return int(m.group(1)) * _UNIT_DAYS[m.group(2)]

    try:
        dt = datetime.fromisoformat(s.replace("z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((now - dt).total_seconds() / 86400, 0.0)
    except ValueError:
        pass

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%m/%d/%Y", "%b %d", "%B %d"):
        yearless = "%Y" not in fmt
        try:
            dt = (
                datetime.strptime(f"{s} {now.year}", fmt + " %Y") if yearless else datetime.strptime(s, fmt)
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if yearless:
            if dt > now + timedelta(days=1):  # "Dec 28" seen in January means last year
                dt = dt.replace(year=now.year - 1)
        return max((now - dt).total_seconds() / 86400, 0.0)
    return None


def is_fresh(raw: Optional[str], max_age_days: float, now: Optional[datetime] = None) -> bool:
    """Undated postings count as fresh (we alert the first time we see them)."""
    age = age_days(raw, now)
    return age is None or age <= max_age_days


def days_ago_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

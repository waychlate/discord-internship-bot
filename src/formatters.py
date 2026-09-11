import re
from datetime import datetime, timezone
from typing import Optional, Tuple


def extract_season(title: str = "", terms: Optional[str] = None, source_name: str = "", url: str = "") -> str:
    """
    Extracts season & year (e.g. Summer 2026, Winter 2026, Spring 2026, Fall 2025).
    Returns a nicely formatted string with emoji.
    """
    search_texts = [terms or "", title, source_name, url]
    full_text = " ".join(search_texts)

    # 1. Match Season with 4-digit Year (e.g. "Summer 2026", "Fall 2025", "Winter 2027")
    match_year = re.search(
        r"\b(Summer|Winter|Spring|Fall|Autumn)\s*[-/]?\s*(202[4-9])\b",
        full_text,
        re.IGNORECASE,
    )
    if match_year:
        season = match_year.group(1).capitalize()
        if season == "Autumn":
            season = "Fall"
        year = match_year.group(2)
        emoji = {"Summer": "☀️", "Winter": "❄️", "Spring": "🌱", "Fall": "🍂"}.get(season, "📅")
        return f"{emoji} {season} {year}"

    # 2. Match Year alone if 2026 / 2027 (often implies Summer of that year in internship repos)
    match_yr_alone = re.search(r"\b(202[5-9])\b", full_text)
    year_val = match_yr_alone.group(1) if match_yr_alone else ""

    # 3. Match Season without year
    match_season = re.search(
        r"\b(Summer|Winter|Spring|Fall|Autumn)\b",
        full_text,
        re.IGNORECASE,
    )
    if match_season:
        season = match_season.group(1).capitalize()
        if season == "Autumn":
            season = "Fall"
        emoji = {"Summer": "☀️", "Winter": "❄️", "Spring": "🌱", "Fall": "🍂"}.get(season, "📅")
        return f"{emoji} {season}" + (f" {year_val}" if year_val else "")

    # 4. Check for Co-op / Off-Season
    if re.search(r"\b(co-op|coop|off-season|year-round)\b", full_text, re.IGNORECASE):
        return f"🔄 Co-op" + (f" {year_val}" if year_val else "")

    if year_val:
        return f"📅 {year_val} Term"

    return "📅 Flexible / Not Specified"


def format_posted_date(date_raw: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Parses and formats raw date/age string into:
    (human_display_string, optional_iso_timestamp_for_embed)
    """
    if not date_raw:
        now_utc = datetime.now(timezone.utc)
        return "Just now (Discovered)", now_utc.isoformat()

    date_str = str(date_raw).strip()

    # Relative shorthands from markdown (e.g. 15d, 2w, 1mo, 3h, 5m, 1y)
    rel_match = re.match(r"^(\d+)\s*([dhwmy])$", date_str, re.IGNORECASE)
    if rel_match:
        num = rel_match.group(1)
        unit = rel_match.group(2).lower()
        unit_map = {
            "m": "minute" if num == "1" else "minutes",
            "h": "hour" if num == "1" else "hours",
            "d": "day" if num == "1" else "days",
            "w": "week" if num == "1" else "weeks",
            "y": "year" if num == "1" else "years",
        }
        if unit == "m" and int(num) > 12:  # might be months if capitalized or in tables
            unit_str = "months"
        else:
            unit_str = unit_map.get(unit, "days")
        return f"{num} {unit_str} ago", datetime.now(timezone.utc).isoformat()

    if date_str.lower() in ["1mo", "2mo", "3mo", "4mo", "5mo", "6mo"]:
        num = date_str[0]
        return f"{num} month{'s' if num != '1' else ''} ago", datetime.now(timezone.utc).isoformat()

    # Try ISO formats (e.g. 2026-08-15T14:20:10Z, 2026-08-15T14:20:10-04:00)
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Format as readable e.g. "Aug 15, 2026 • 14:20 UTC"
        dt_utc = dt.astimezone(timezone.utc)
        display = dt_utc.strftime("%b %d, %Y • %H:%M UTC")
        return display, dt_utc.isoformat()
    except (ValueError, TypeError):
        pass

    # Try standard date strings like "May 1", "Jul 28", "2026-05-01"
    for fmt in ("%b %d", "%B %d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            # If no year was in format, set current year
            if "%Y" not in fmt:
                dt = dt.replace(year=datetime.now(timezone.utc).year)
            display = dt.strftime("%b %d, %Y")
            return display, dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    # Fallback to whatever string was scraped
    return date_str, datetime.now(timezone.utc).isoformat()


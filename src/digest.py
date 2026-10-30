"""Daily digest: one Discord message summarizing the last 24h of matches, ranked by Gemini when available."""
import logging
import os
from datetime import datetime
from typing import List, Optional

import requests

from src.formatters import tier_label
from src.models import JobPosting

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DISCORD_LIMIT = 2000

PROFILE = (
    "UF Electrical Engineering sophomore looking for internships. Priority: embedded systems / firmware first, "
    "then hardware, FPGA, and edge ML. Skills: C/C++, FreeRTOS, ESP-IDF, STM32, KiCad PCB design, PyTorch / edge ML."
)


def _job_line(j: JobPosting) -> str:
    kind = f" [{j.company_type}]" if j.company_type else ""
    return f"{j.company}{kind} | {j.title} | {tier_label(j.tier)} | {j.location} | {j.url}"


def gemini_digest(jobs: List[JobPosting], timeout: float = 30) -> Optional[str]:
    """Ranked digest text from Gemini, or None if no key / request failed / reply looks like junk."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    prompt = (
        f"Candidate profile: {PROFILE}\n\n"
        "Rank these internship postings best-fit first for this candidate. For each, output one Discord-markdown "
        "line: `N. **Company** - Title - <link>` then ` - ` and a one-line why-it-fits. Use the exact link given, "
        "wrapped in <>. No intro, no outro, keep the whole reply under 1800 characters if possible.\n\n"
        + "\n".join(_job_line(j) for j in jobs)
    )
    try:
        # key goes in a header, not the URL, so it can't leak into exception messages or logs
        res = requests.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        if res.status_code != 200:
            logger.warning(f"Gemini digest failed: HTTP {res.status_code}")
            return None
        parts = res.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception as e:
        logger.warning(f"Gemini digest failed: {type(e).__name__}")
        return None
    # Junk guard: must mention at least one real posting link
    if not text or not any(j.url in text for j in jobs):
        logger.warning("Gemini digest reply unusable; using plain fallback")
        return None
    return text


def fallback_digest(jobs: List[JobPosting]) -> str:
    return "\n".join(
        f"{i}. **{j.company}** - {j.title} - {tier_label(j.tier)} - <{j.url}>" for i, j in enumerate(jobs, 1)
    )


def split_message(text: str, limit: int = DISCORD_LIMIT) -> List[str]:
    """Split on line boundaries into chunks <= limit (a single over-long line is hard-cut)."""
    chunks, cur = [], ""
    for line in text.splitlines():
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + 1 + len(line) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def run_digest(db, notifier, dry_run: bool = False) -> bool:
    """Build and send the digest. Returns True when there was nothing to send or it was delivered/printed."""
    jobs = db.undigested_recent(24)
    if not jobs:
        logger.info("Daily digest: no new postings in the last 24h; nothing sent.")
        return True
    body = gemini_digest(jobs) or fallback_digest(jobs)
    text = f"📬 **Daily Internship Digest** ({datetime.now():%b %d}) - {len(jobs)} posting(s)\n{body}"
    chunks = split_message(text)
    if dry_run:
        print("\n---\n".join(chunks))
        return True
    for chunk in chunks:
        if not notifier.send_text(chunk):
            # ponytail: a mid-digest failure resends earlier chunks on retry; fine for a once-a-day message
            logger.error("Daily digest send failed; will retry later")
            return False
    db.mark_digested([j.id for j in jobs])
    logger.info(f"Daily digest sent ({len(jobs)} postings).")
    return True

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
import requests

from src.formatters import extract_season, format_posted_date, tier_label
from src.models import JobPosting

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, config: Dict, webhook_url: Optional[str] = None):
        self.config = config
        notif_cfg = config.get("notification", {})
        
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.bot_name = notif_cfg.get("bot_name", "Internship Radar")
        self.avatar_url = notif_cfg.get("avatar_url", "")
        self.embed_color = notif_cfg.get("embed_color", 3066993)  # Emerald green default
        self.enable_mention = notif_cfg.get("enable_mention", False)
        self.role_id = os.getenv("DISCORD_ROLE_ID") or notif_cfg.get("role_id_to_mention", "")

    def is_configured(self) -> bool:
        return bool(self.webhook_url and "discord.com/api/webhooks" in self.webhook_url)

    def send_notification(self, job: JobPosting) -> bool:
        if not self.is_configured():
            logger.warning("Discord webhook URL is not configured. Skipping notification.")
            return False

        payload = self._build_embed_payload(job)
        return self._post_webhook(payload)

    def send_batch(self, jobs: List[JobPosting]) -> bool:
        """One webhook message with up to 10 embeds (Discord's limit): a single notification for many jobs."""
        if not self.is_configured():
            logger.warning("Discord webhook URL is not configured. Skipping notification.")
            return False
        payloads = [self._build_embed_payload(j) for j in jobs]
        payload = dict(payloads[0])
        payload["embeds"] = [p["embeds"][0] for p in payloads]
        return self._post_webhook(payload)

    def send_text(self, content: str) -> bool:
        """Plain message (<= 2000 chars). Mentions disabled so LLM text can't ping @everyone."""
        if not self.is_configured():
            logger.warning("Discord webhook URL is not configured. Skipping message.")
            return False
        return self._post_webhook({
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "content": content,
            "allowed_mentions": {"parse": []},
        })

    def send_test_message(self) -> bool:
        """Sends a verification test embed to the Discord webhook."""
        if not self.is_configured():
            logger.error("Cannot send test message: DISCORD_WEBHOOK_URL is missing or invalid.")
            return False

        test_payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "embeds": [
                {
                    "title": "⚡ Internship Radar Connected Successfully",
                    "description": "Your Discord webhook is active! You will receive instant notifications whenever new embedded/firmware internship postings (hardware/FPGA/edge-ML in the daily digest) are discovered.",
                    "color": self.embed_color,
                    "fields": [
                        {"name": "Status", "value": "🟢 Online & Monitoring", "inline": True},
                        {"name": "Sources", "value": "GitHub Curated Repos & ATS Feeds", "inline": True},
                    ],
                    "footer": {
                        "text": "Internship Radar • witchs.me"
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
        return self._post_webhook(test_payload)

    def send_seed_summary(self, seeded_count: int, total_scraped: int) -> bool:
        """Sends a single summary message after quietly indexing existing jobs on initial run."""
        if not self.is_configured():
            return False

        payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "embeds": [
                {
                    "title": "🟢 Internship Radar Initialized",
                    "description": (
                        f"Indexed **{seeded_count}** existing matching internship positions (from {total_scraped} total postings).\n\n"
                        f"Database is seeded! Going forward, **you will only receive alerts for new openings**."
                    ),
                    "color": self.embed_color,
                    "fields": [
                        {"name": "Seeded Postings", "value": str(seeded_count), "inline": True},
                        {"name": "Monitoring Mode", "value": "⚡ Instant Alerts for New Jobs", "inline": True},
                    ],
                    "footer": {
                        "text": "Internship Radar • Monitoring Active"
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
        return self._post_webhook(payload)

    def _build_embed_payload(self, job: JobPosting) -> Dict:
        tags_str = ", ".join([f"`{kw}`" for kw in job.matched_keywords]) if job.matched_keywords else "N/A"
        
        season_str = extract_season(
            title=job.title,
            terms=job.terms,
            source_name=job.source,
            url=job.url,
        )

        date_display, iso_timestamp = format_posted_date(job.date_posted)

        fields = [
            {"name": "🏢 Company", "value": job.company, "inline": True},
            {"name": "📍 Location", "value": job.location or "Not specified", "inline": True},
            {"name": "📅 Season / Term", "value": season_str, "inline": True},
            {"name": "🕒 Posted", "value": date_display, "inline": True},
            {"name": "🧭 Tier", "value": tier_label(job.tier), "inline": True},
            {"name": "🏷️ Company Type", "value": job.company_type or "unknown", "inline": True},
            {"name": "🔎 Matched Tags", "value": tags_str, "inline": False},
            {"name": "📡 Source", "value": job.source, "inline": True},
        ]

        embed = {
            "title": f"🎯 {job.title}",
            "url": job.url,
            "color": self.embed_color,
            "fields": fields,
            "timestamp": iso_timestamp,
            "footer": {
                "text": f"Internship Radar • ID: {job.id}"
            },
        }

        content = ""
        if self.enable_mention and self.role_id:
            content = f"<@&{self.role_id}> New internship posting found!"

        payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "content": content,
            "embeds": [embed],
        }
        return payload

    def _post_webhook(self, payload: Dict, retries: int = 3) -> bool:
        for attempt in range(retries):
            try:
                res = requests.post(self.webhook_url, json=payload, timeout=10)
                if res.status_code in [200, 204]:
                    return True
                elif res.status_code == 429:
                    retry_after = res.json().get("retry_after", 2)
                    logger.warning(f"Rate limited by Discord. Sleeping for {retry_after}s...")
                    time.sleep(retry_after)
                else:
                    logger.error(f"Failed to send webhook: HTTP {res.status_code} - {res.text}")
                    return False
            except Exception as e:
                # type only: requests exceptions embed the URL, which contains the webhook token
                logger.error(f"Error posting to Discord Webhook: {type(e).__name__}")
                time.sleep(1)

        return False

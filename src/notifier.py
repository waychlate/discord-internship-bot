import logging
import os
import time
from typing import Dict, Optional
import requests

from src.models import JobPosting

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, config: Dict, webhook_url: Optional[str] = None):
        self.config = config
        notif_cfg = config.get("notification", {})
        
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.bot_name = notif_cfg.get("bot_name", "ECE Job Radar")
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
                    "title": "⚡ ECE Job Radar Connected Successfully",
                    "description": "Your Discord webhook is active! You will receive instant notifications whenever new ECE, Embedded, FPGA, or Hardware internship postings are discovered.",
                    "color": self.embed_color,
                    "fields": [
                        {"name": "Status", "value": "🟢 Online & Monitoring", "inline": True},
                        {"name": "Sources", "value": "GitHub Curated Repos & ATS Feeds", "inline": True},
                    ],
                    "footer": {
                        "text": "ECE Job Radar • witchs.me"
                    },
                }
            ],
        }
        return self._post_webhook(test_payload)

    def _build_embed_payload(self, job: JobPosting) -> Dict:
        tags_str = ", ".join([f"`{kw}`" for kw in job.matched_keywords]) if job.matched_keywords else "N/A"
        
        fields = [
            {"name": "🏢 Company", "value": job.company, "inline": True},
            {"name": "📍 Location", "value": job.location or "Not specified", "inline": True},
        ]

        if job.terms:
            fields.append({"name": "📅 Term", "value": job.terms, "inline": True})

        fields.append({"name": "🏷️ Matched ECE Tags", "value": tags_str, "inline": False})
        fields.append({"name": "📡 Source", "value": job.source, "inline": True})

        embed = {
            "title": f"🎯 {job.title}",
            "url": job.url,
            "color": self.embed_color,
            "fields": fields,
            "footer": {
                "text": f"ECE Job Radar • ID: {job.id}"
            },
        }

        content = ""
        if self.enable_mention and self.role_id:
            content = f"<@&{self.role_id}> New ECE internship posting found!"

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
                logger.error(f"Error posting to Discord Webhook: {e}")
                time.sleep(1)

        return False


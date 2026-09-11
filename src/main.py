import argparse
import logging
import os
import signal
import sys
import time
from typing import Dict, List
import yaml
from dotenv import load_dotenv

from src.db import Database
from src.filter import ECEFilter
from src.models import JobPosting
from src.notifier import DiscordNotifier
from src.sources.ats_boards import ATSBoardSource
from src.sources.base import BaseSource
from src.sources.github_markdown import GitHubMarkdownSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ece_scraper")

running = True


def handle_shutdown(signum, frame):
    global running
    logger.info("Shutdown signal received. Finishing current cycle and stopping...")
    running = False


def load_config(config_path: str = "config.yaml") -> Dict:
    if not os.path.exists(config_path):
        logger.warning(f"Config file {config_path} not found. Using defaults.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def init_sources(config: Dict) -> List[BaseSource]:
    sources: List[BaseSource] = []
    sources_cfg = config.get("sources", {})

    # GitHub Repos
    github_repos = sources_cfg.get("github_repositories", [])
    for repo in github_repos:
        name = repo.get("name", "GitHub Repo")
        url = repo.get("url")
        if url:
            sources.append(GitHubMarkdownSource(name, url, config))

    # ATS Boards (Greenhouse / Lever)
    if sources_cfg.get("greenhouse_boards") or sources_cfg.get("lever_boards"):
        sources.append(ATSBoardSource("Company ATS Boards", config))

    return sources


def run_scrape_cycle(
    sources: List[BaseSource],
    ece_filter: ECEFilter,
    db: Database,
    notifier: DiscordNotifier,
    config: Dict,
    dry_run: bool = False,
):
    logger.info("================ Starting Scrape Cycle ================")
    total_found = 0
    total_matched = 0
    total_new = 0

    scraper_cfg = config.get("scraper", {})
    quiet_seed = scraper_cfg.get("quiet_initial_seed", True) and (db.get_total_count() == 0)
    max_alerts = scraper_cfg.get("max_alerts_per_cycle", 10)

    if quiet_seed:
        logger.info("First run on fresh database detected: Performing quiet initial seed (indexing existing positions without spamming Discord)...")

    for source in sources:
        try:
            raw_jobs = source.fetch_jobs()
            total_found += len(raw_jobs)

            for job in raw_jobs:
                is_match, matched_tags = ece_filter.evaluate(job)
                if is_match:
                    total_matched += 1
                    
                    if dry_run:
                        logger.info(
                            f"[DRY-RUN MATCH] {job.company} - {job.title} | Tags: {matched_tags} | URL: {job.url}"
                        )
                        continue

                    # Check if already seen in DB
                    if not db.is_job_seen(job.id):
                        db.save_job(job)
                        total_new += 1

                        if quiet_seed:
                            # In quiet seed mode, save all existing jobs without sending individual embeds
                            continue

                        if total_new > max_alerts:
                            logger.warning(
                                f"Reached max alert limit ({max_alerts}) for this cycle. Additional jobs will be indexed silently."
                            )
                            continue

                        logger.info(
                            f"⚡ NEW ECE JOB FOUND: {job.company} - {job.title} ({', '.join(matched_tags)})"
                        )
                        # Send Discord Notification
                        success = notifier.send_notification(job)
                        if success:
                            time.sleep(1.5)
                        else:
                            logger.error(f"Failed to send Discord alert for job {job.id}")
        except Exception as e:
            logger.error(f"Error processing source {source.name}: {e}", exc_info=True)

    if quiet_seed and not dry_run:
        logger.info(f"Initial seed complete: {total_matched} existing ECE jobs indexed. Sending summary to Discord...")
        notifier.send_seed_summary(total_matched, total_found)

    alerts_sent = 0 if quiet_seed else min(total_new, max_alerts)
    logger.info(
        f"Cycle Summary: Raw Found: {total_found} | ECE Matches: {total_matched} | New Alerts Sent: {alerts_sent} | Total Stored: {db.get_total_count()}"
    )
    logger.info("================ Scrape Cycle Completed ================")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="ECE Internship Discord Scraper & Notifier")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Run once without saving to DB or sending webhooks")
    parser.add_argument("--test-webhook", action="store_true", help="Send a test embed to Discord and exit")
    parser.add_argument("--once", action="store_true", help="Run a single scrape cycle and exit")
    args = parser.parse_args()

    config = load_config(args.config)
    db_path = config.get("scraper", {}).get("db_path", "data/jobs.db")
    db = Database(db_path)
    ece_filter = ECEFilter(config)
    notifier = DiscordNotifier(config)

    if args.test_webhook:
        logger.info("Testing Discord Webhook connection...")
        if notifier.send_test_message():
            logger.info("✅ Test message sent successfully to Discord!")
            sys.exit(0)
        else:
            logger.error("❌ Failed to send test message. Check your DISCORD_WEBHOOK_URL in .env")
            sys.exit(1)

    sources = init_sources(config)
    logger.info(f"Initialized {len(sources)} scraping source(s).")

    if args.dry_run or args.once:
        run_scrape_cycle(sources, ece_filter, db, notifier, config, dry_run=args.dry_run)
        return

    # Continuous Scheduled Loop
    interval_minutes = int(
        os.getenv("SCRAPE_INTERVAL_MINUTES")
        or config.get("scraper", {}).get("interval_minutes", 30)
    )
    logger.info(f"Starting continuous scraper daemon. Interval: every {interval_minutes} minutes.")

    # Register signal handlers for clean container exit
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Run initial cycle immediately
    run_scrape_cycle(sources, ece_filter, db, notifier, config)

    # Loop with sleep intervals
    while running:
        logger.info(f"Sleeping for {interval_minutes} minutes until next cycle...")
        for _ in range(interval_minutes * 60):
            if not running:
                break
            time.sleep(1)

        if running:
            run_scrape_cycle(sources, ece_filter, db, notifier, config)

    logger.info("ECE Scraper daemon stopped gracefully.")


if __name__ == "__main__":
    main()

import argparse
import logging
import os
import signal
import sys
import time
from typing import Dict, List
import yaml
from dotenv import load_dotenv

from src.dates import age_days, is_fresh
from src.db import Database
from src.filter import ECEFilter
from src.models import JobPosting
from src.notifier import DiscordNotifier
from src.sources.ats_boards import ATSBoardSource
from src.sources.base import BaseSource
from src.sources.github_markdown import GitHubMarkdownSource
from src.sources.keyword_search import AdzunaSource, USAJobsSource
from src.sources.page_watch import PageWatchSource

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
    for repo in sources_cfg.get("github_repositories", []):
        if repo.get("url"):
            sources.append(
                GitHubMarkdownSource(
                    repo.get("name", "GitHub Repo"), repo["url"], config, repo.get("internships_only", False)
                )
            )

    # Company ATS boards (Greenhouse / Lever / Ashby / SmartRecruiters / Workday)
    if sources_cfg.get("companies"):
        sources.append(ATSBoardSource("Company ATS Boards", config))

    # Keyword-search APIs (only active when their keys are in .env)
    for search in (AdzunaSource(config), USAJobsSource(config)):
        if search.enabled():
            sources.append(search)
        else:
            logger.info(f"{search.name} disabled (missing API keys in .env or no keyword_search.queries)")

    for watch in config.get("page_watchers", []):
        sources.append(PageWatchSource(watch, config))

    return sources


def drip_gap(pending: int, config: Dict) -> float:
    """Seconds to wait before the next message so the queue drains within drip_window_minutes.
    Small queues wait at most drip_max_gap_seconds; big ones are stretched to fit the window."""
    cfg = config.get("scraper", {})
    batch = cfg.get("alert_batch_size", 10)
    window = cfg.get("drip_window_minutes", 60) * 60
    messages = -(-max(pending, 1) // batch)  # ceil
    return min(cfg.get("drip_max_gap_seconds", 120), window / messages)


def send_next_batch(db: Database, notifier: DiscordNotifier, config: Dict) -> bool:
    """Send the oldest queued alerts as one message. Returns False when nothing was sent (empty or failed)."""
    jobs = db.pending_batch(config.get("scraper", {}).get("alert_batch_size", 10))
    if not jobs:
        return False
    logger.info(f"⚡ SENDING {len(jobs)} JOB ALERT(S): " + "; ".join(f"{j.company} - {j.title}" for j in jobs))
    if notifier.send_batch(jobs):
        sent = jobs
    else:
        # e.g. Discord rejects >6000 chars of embed text per message: retry one by one so the queue can't jam
        sent = [j for j in jobs if notifier.send_notification(j)] if len(jobs) > 1 else []
    if not sent:
        logger.error("Failed to send Discord alert batch; will retry")
        return False
    for j in sent:
        db.mark_sent(j.id)
    return True


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
    max_age_days = scraper_cfg.get("max_age_days", 2)

    if quiet_seed:
        logger.info("First run on fresh database detected: Performing quiet initial seed (indexing existing positions without spamming Discord)...")

    for source in sources:
        try:
            raw_jobs = source.fetch_jobs()
            total_found += len(raw_jobs)

            for job in raw_jobs:
                if not job.pre_approved:
                    if not is_fresh(job.date_posted, max_age_days):
                        continue
                    is_match, matched_tags = ece_filter.evaluate(job)
                    if not is_match:
                        continue
                else:
                    matched_tags = job.matched_keywords
                total_matched += 1

                if dry_run:
                    logger.info(
                        f"[DRY-RUN MATCH] {job.company} - {job.title} | Age: {age_days(job.date_posted)} days | Tags: {matched_tags} | URL: {job.url}"
                    )
                    continue

                if db.is_duplicate(job):
                    continue
                # Quiet seed indexes without alerting; otherwise queue it for the drip sender
                db.save_job(job, status="seen" if quiet_seed else "pending")
                total_new += 1
        except Exception as e:
            logger.error(f"Error processing source {source.name}: {e}", exc_info=True)

    if quiet_seed and not dry_run:
        logger.info(f"Initial seed complete: {total_matched} existing ECE jobs indexed. Sending summary to Discord...")
        notifier.send_seed_summary(total_matched, total_found)

    logger.info(
        f"Cycle Summary: Raw Found: {total_found} | Fresh Matches: {total_matched} | New: {total_new} | "
        f"Queued: {db.pending_count()} | Total Stored: {db.get_total_count()}"
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
        while args.once and not args.dry_run and send_next_batch(db, notifier, config):
            time.sleep(1.5)  # --once flushes the whole queue immediately instead of dripping
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

    # Scraping and alert sending run on separate timers: cycles enqueue, the drip sender
    # paces Discord alerts (see drip_gap).
    next_cycle = next_send = 0.0
    while running:
        now = time.monotonic()
        if now >= next_cycle:
            run_scrape_cycle(sources, ece_filter, db, notifier, config)
            next_cycle = time.monotonic() + interval_minutes * 60
            logger.info(f"Next scrape cycle in {interval_minutes} minutes.")
        if now >= next_send:
            if send_next_batch(db, notifier, config):
                next_send = time.monotonic() + drip_gap(db.pending_count(), config)
            elif db.pending_count():
                next_send = time.monotonic() + 60  # send failed; retry in a minute
        time.sleep(1)

    logger.info("ECE Scraper daemon stopped gracefully.")


if __name__ == "__main__":
    main()

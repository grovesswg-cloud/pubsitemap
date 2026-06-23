#!/usr/bin/env python3
"""LORD Automation — Scheduler & Entry Point

Run modes:
  python scheduler.py --run-now    Single cycle (used by GitHub Actions)
  python scheduler.py              Persistent daemon with schedule (local use)
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from config import PUBLISH_TIMES_UTC, MAX_BULLETINS_PER_DAY
from news_fetcher import get_trending_music_news
from article_writer import write_bulletin
from image_sourcer import get_article_image
from publisher import publish_article, load_index, is_duplicate, count_today

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  [LORD]  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('lord')


def run_cycle() -> bool:
    """
    Execute one publication cycle.
    Returns True if an article was published, False otherwise.
    """
    log.info("─── Publication cycle starting ───────────────────────────")

    index = load_index()
    today_count = count_today(index)
    log.info("Bulletins published today: %d / %d", today_count, MAX_BULLETINS_PER_DAY)

    if today_count >= MAX_BULLETINS_PER_DAY:
        log.info("Daily limit reached — skipping cycle.")
        return False

    # Fetch news
    log.info("Fetching music news...")
    news_items = get_trending_music_news()
    log.info("Retrieved %d news items", len(news_items))

    if not news_items:
        log.warning("No news items available — cycle aborted.")
        return False

    # Select first unpublished item
    selected = None
    for item in news_items:
        if not is_duplicate(item['title'], index):
            selected = item
            break

    if not selected:
        log.warning("All current news items already published — cycle aborted.")
        return False

    log.info("Selected: %s", selected['title'][:80])

    # Write article
    log.info("Writing article...")
    article_data = write_bulletin(selected)
    log.info("Article written: %s", article_data.get('title', '')[:60])

    # Source image
    image_query = article_data.get('imageQuery', 'concert music performance')
    log.info("Sourcing image: '%s'", image_query)
    image = get_article_image(image_query)
    if image:
        log.info("Image sourced from %s: %s", image['provider'], image['credit'])
    else:
        log.info("No image sourced — article will use branded placeholder")

    # Publish
    entry = publish_article(article_data, image)
    log.info("Published: %s", entry['url'])
    log.info("─────────────────────────────────────────────────────────")
    return True


def run_daemon() -> None:
    """Run as a persistent scheduler (local / server use)."""
    try:
        import schedule
    except ImportError:
        log.error("'schedule' package not installed. Run: pip install schedule")
        sys.exit(1)

    log.info("LORD Scheduler starting. Publishing at UTC: %s", ', '.join(PUBLISH_TIMES_UTC))
    for t in PUBLISH_TIMES_UTC:
        schedule.every().day.at(t).do(run_cycle)

    import time
    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(description='LORD Automated Publisher')
    parser.add_argument(
        '--run-now',
        action='store_true',
        help='Run one publication cycle immediately and exit (for CI/Actions)',
    )
    args = parser.parse_args()

    if args.run_now:
        success = run_cycle()
        sys.exit(0 if success else 0)  # Always exit 0 to not fail the CI step
    else:
        run_daemon()


if __name__ == '__main__':
    main()

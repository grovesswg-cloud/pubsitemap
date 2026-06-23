#!/usr/bin/env python3
"""LORD Automation — Scheduler & Entry Point

Run modes:
  python scheduler.py --run-now                      Publish one bulletin (default)
  python scheduler.py --run-now --type feature       Publish one feature
  python scheduler.py --run-now --type review        Publish a current album review
  python scheduler.py --run-now --type classic-review  Publish a classic album review
  python scheduler.py                                Persistent daemon (local use)
"""
import argparse
import logging
import sys

from config import PUBLISH_TIMES_UTC, MAX_BULLETINS_PER_DAY
from news_fetcher import get_trending_music_news
from article_writer import write_bulletin
from feature_writer import write_feature
from review_writer import write_review, write_classic_review
from album_finder import extract_album_from_news, pick_classic_album, _get_reviewed_albums
from image_sourcer import get_article_image, get_article_images
from publisher import publish_article, load_index, is_duplicate, count_today

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  [LORD]  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('lord')


def _check_api_key() -> bool:
    from config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set. Add it as a GitHub Actions secret.")
        log.error("Go to: repo → Settings → Secrets and variables → Actions → New secret")
        return False
    return True


def _source_images(article_data: dict, fallback_query: str = 'concert music performance') -> list:
    """
    Fetch images for an article.
    Uses imageQueries list if present (multi-image), otherwise imageQuery (single).
    Returns a list of image dicts (index 0 = hero, rest = inline).
    """
    queries = article_data.get('imageQueries') or []
    if not queries:
        single = article_data.get('imageQuery', '') or fallback_query
        queries = [single]

    log.info("Sourcing %d image(s): %s", len(queries), queries[:3])
    images = get_article_images(queries)

    if images:
        for img in images:
            log.info("  [%s] %s", img.get('provider', '?'), img.get('credit', ''))
    else:
        log.info("No images sourced — article will use branded placeholder")
    return images


def run_cycle() -> bool:
    """Execute one bulletin publication cycle."""
    log.info("─── Bulletin cycle starting ───────────────────────────────")
    try:
        if not _check_api_key():
            return False

        index = load_index()
        today_count = count_today(index)
        log.info("Bulletins published today: %d / %d", today_count, MAX_BULLETINS_PER_DAY)

        if today_count >= MAX_BULLETINS_PER_DAY:
            log.info("Daily limit reached — skipping cycle.")
            return False

        log.info("Fetching music news...")
        news_items = get_trending_music_news()
        log.info("Retrieved %d music news items", len(news_items))

        if not news_items:
            log.warning("No news items available — cycle aborted.")
            return False

        selected = None
        for item in news_items:
            if not is_duplicate(item['title'], index):
                selected = item
                break

        if not selected:
            log.warning("All current news items already published — cycle aborted.")
            return False

        log.info("Selected: %s", selected['title'][:80])

        log.info("Writing bulletin...")
        article_data = write_bulletin(selected)
        log.info("Written: %s", article_data.get('title', '')[:60])

        images = _source_images(article_data)
        entry = publish_article(article_data, images)
        log.info("Published: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        return True

    except Exception as exc:
        log.error("Bulletin cycle failed: %s", exc, exc_info=True)
        return False


def feature_cycle() -> bool:
    """Execute one feature publication cycle."""
    log.info("─── Feature cycle starting ────────────────────────────────")
    try:
        if not _check_api_key():
            return False

        log.info("Fetching music news for feature inspiration...")
        news_items = get_trending_music_news()
        log.info("Retrieved %d music news items", len(news_items))

        if not news_items:
            log.warning("No news items available — feature cycle aborted.")
            return False

        index = load_index()
        selected = None
        for item in news_items:
            if not is_duplicate(item['title'], index):
                selected = item
                break

        if not selected:
            log.warning("No fresh news for feature inspiration — aborted.")
            return False

        log.info("Writing feature inspired by: %s", selected['title'][:80])
        article_data = write_feature(selected)
        log.info("Written: %s", article_data.get('title', '')[:60])

        images = _source_images(article_data, 'musician portrait studio')
        entry = publish_article(article_data, images)
        log.info("Published feature: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        return True

    except Exception as exc:
        log.error("Feature cycle failed: %s", exc, exc_info=True)
        return False


def review_cycle() -> bool:
    """Execute one current album review cycle."""
    log.info("─── Review cycle starting ─────────────────────────────────")
    try:
        if not _check_api_key():
            return False

        log.info("Fetching music news to find current album releases...")
        news_items = get_trending_music_news()
        log.info("Retrieved %d music news items", len(news_items))

        if not news_items:
            log.warning("No news items available — review cycle aborted.")
            return False

        index = load_index()
        reviewed = _get_reviewed_albums(index)
        log.info("Albums already reviewed: %d", len(reviewed))

        log.info("Identifying current album from news...")
        album_info = extract_album_from_news(news_items)

        if not album_info:
            log.warning("Could not identify a current album from news — review cycle aborted.")
            return False

        log.info("Writing review: %s — %s", album_info['artist'], album_info['album'])
        article_data = write_review(album_info)
        log.info("Written: %s [%s]", article_data.get('title', '')[:60], article_data.get('rating', ''))

        images = _source_images(article_data, 'vinyl record music studio')
        entry = publish_article(article_data, images)
        log.info("Published review: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        return True

    except Exception as exc:
        log.error("Review cycle failed: %s", exc, exc_info=True)
        return False


def classic_review_cycle() -> bool:
    """Execute one classic album (historical reassessment) review cycle."""
    log.info("─── Classic Review cycle starting ─────────────────────────")
    try:
        if not _check_api_key():
            return False

        index = load_index()
        reviewed = _get_reviewed_albums(index)
        log.info("Albums already reviewed: %d", len(reviewed))

        log.info("Selecting classic album for reassessment...")
        album_info = pick_classic_album(reviewed)
        log.info("Selected: %s — %s (%s)", album_info['artist'], album_info['album'], album_info.get('year', ''))

        article_data = write_classic_review(album_info)
        log.info("Written: %s [%s]", article_data.get('title', '')[:60], article_data.get('rating', ''))

        images = _source_images(article_data, 'vintage vinyl record collection')
        entry = publish_article(article_data, images)
        log.info("Published classic review: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        return True

    except Exception as exc:
        log.error("Classic review cycle failed: %s", exc, exc_info=True)
        return False


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
        help='Run one cycle immediately and exit (for CI/Actions)',
    )
    parser.add_argument(
        '--type',
        default='bulletin',
        choices=['bulletin', 'feature', 'review', 'classic-review'],
        help='Content type to publish (default: bulletin)',
    )
    args = parser.parse_args()

    if args.run_now:
        dispatch = {
            'bulletin':       run_cycle,
            'feature':        feature_cycle,
            'review':         review_cycle,
            'classic-review': classic_review_cycle,
        }
        dispatch[args.type]()
        sys.exit(0)  # Always exit 0 — never fail the CI step
    else:
        run_daemon()


if __name__ == '__main__':
    main()

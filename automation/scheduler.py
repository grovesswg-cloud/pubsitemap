#!/usr/bin/env python3
"""LORD Automation — Scheduler & Entry Point

Run modes:
  python scheduler.py --run-now                                    Publish one bulletin (default)
  python scheduler.py --run-now --type feature                     Publish one feature
  python scheduler.py --run-now --type review                      Publish a current album review
  python scheduler.py --run-now --type classic-review              Publish a classic album review
  python scheduler.py --run-now --type classic-review \\
    --target-artist "Massive Attack" --target-album "Mezzanine"    Force a specific album (Golden Article / QA)
  python scheduler.py                                              Persistent daemon (local use)
"""
import argparse
import logging
import sys

from config import (
    PUBLISH_TIMES_UTC, MAX_BULLETINS_PER_DAY, MAX_FEATURES_PER_DAY, MAX_REVIEWS_PER_DAY,
    QUALITY_METADATA_VALIDATION, QUALITY_FACT_VERIFICATION, QUALITY_FACT_FAIL_OPEN,
    QUALITY_IMAGE_VALIDATION, QUALITY_IMAGE_FAIL_OPEN,
    QUALITY_EDITORIAL_REVIEW, QUALITY_EDITORIAL_FAIL_OPEN,
    QUALITY_SEO_VALIDATION,
    GOOGLE_GEMINI_API_KEY,
)
from news_fetcher import get_trending_music_news
from article_writer import write_bulletin
from feature_writer import write_feature
from review_writer import write_review, write_classic_review
from album_finder import extract_album_from_news, pick_classic_album, _get_reviewed_albums, is_already_reviewed
from image_sourcer import get_article_image, get_article_images
from publisher import publish_article, load_index, is_duplicate, is_artist_covered, count_today, count_today_by_type
from validators.metadata import validate_metadata

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


_fact_provider              = None
_vision_provider            = None
_editorial_provider         = None
_search_readiness_provider  = None

# Albums selected this process lifetime that failed to publish (wrong image, parse error, etc.).
# Passed to pick_classic_album() so the same candidate isn't re-selected in daemon mode.
_classic_attempted: list[str] = []


def _get_fact_provider():
    global _fact_provider
    if _fact_provider is None:
        from providers.impl.gemini_fact import GeminiFactProvider
        _fact_provider = GeminiFactProvider(api_key=GOOGLE_GEMINI_API_KEY)
    return _fact_provider


def _get_vision_provider():
    global _vision_provider
    if _vision_provider is None:
        from providers.impl.gemini_vision import GeminiVisionProvider
        _vision_provider = GeminiVisionProvider(api_key=GOOGLE_GEMINI_API_KEY)
    return _vision_provider


def _fetch_image_bytes(image_url: str) -> tuple[bytes, str] | None:
    """Download image bytes and mime type. Returns None on failure."""
    import requests
    try:
        resp = requests.get(image_url, timeout=15, headers={'User-Agent': 'LORD/1.0'})
        resp.raise_for_status()
        mime_type = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
        if mime_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif'):
            mime_type = 'image/jpeg'
        return resp.content, mime_type
    except Exception as exc:
        log.warning("Vision QA: failed to fetch image %s: %s", image_url, exc)
        return None


def _check_one_image(image: dict, article_data: dict, role: str, image_index: int = 0) -> bool:
    """
    Run vision + entity identity check on a single image.
    role: 'hero' or 'inline', image_index: position in the images list (0-based).
    Returns True if the image passes (or gate is disabled).
    """
    if not QUALITY_IMAGE_VALIDATION:
        return True
    if not GOOGLE_GEMINI_API_KEY:
        log.warning("QUALITY_IMAGE_VALIDATION=true but GOOGLE_GEMINI_API_KEY not set — skipping gate.")
        return True

    image_url = image.get('url', '')
    if not image_url:
        log.warning("Vision QA: no URL on %s image (idx=%d) — skipping.", role, image_index)
        return True

    fetched = _fetch_image_bytes(image_url)
    if fetched is None:
        if QUALITY_IMAGE_FAIL_OPEN:
            log.warning("Image fetch failed (%s idx=%d) — proceeding (fail-open mode).", role, image_index)
            return True
        log.error(
            "Image fetch failed (%s idx=%d) — blocking (fail-closed). Set QUALITY_IMAGE_FAIL_OPEN=true to allow through.",
            role, image_index,
        )
        return False
    image_bytes, mime_type = fetched

    provider = _get_vision_provider()
    result   = provider.verify_image(image_bytes, mime_type, article_data)

    for w in result.warnings:
        log.warning("VISION WARN [%s|idx=%d]: %s", role, image_index, w)

    tier = image.get('evidenceTier', 'UNKNOWN')
    log.info(
        "VISION [%s|idx=%d|tier=%s]: %s (confidence: %.2f, person=%s, entity=%s, technical=%s, editorial=%s)",
        role, image_index, tier, result.result, result.confidence,
        result.person_match, result.entity_match, result.technical_pass,
        result.editorial_quality,
    )

    if result.result == 'FAIL':
        for e in result.errors:
            log.error("VISION FAIL [%s|idx=%d]: %s", role, image_index, e)
        if not result.entity_match:
            log.error(
                "VISION ENTITY MISMATCH [%s|idx=%d]: expected=%r detected=%r confidence=%.2f reason=%s",
                role, image_index,
                result.expected_entity, result.detected_entity,
                result.entity_confidence, result.mismatch_reason,
            )
        return False

    if result.result == 'UNCERTAIN':
        if QUALITY_IMAGE_FAIL_OPEN:
            log.warning("Vision uncertain [%s|idx=%d] — proceeding (fail-open mode).", role, image_index)
        else:
            log.error(
                "Vision uncertain [%s|idx=%d] — blocking (fail-closed, default). "
                "Set QUALITY_IMAGE_FAIL_OPEN=true to allow uncertain results through.",
                role, image_index,
            )
            return False

    return True


def _run_vision_verification(images: list, article_data: dict) -> list:
    """
    Run vision/entity verification on all images.

    Hero (images[0]): failure blocks publication — returns empty list.
    Inline images: failure drops that image only; others continue.

    Returns the verified image list (hero + passing inlines), or [] to signal abort.
    """
    if not images:
        return []

    # Hero is mandatory — block the article if it fails
    if not _check_one_image(images[0], article_data, role='hero', image_index=0):
        log.error(
            "Hero image failed vision verification for '%s' — skipping article.",
            article_data.get('title', '')[:60],
        )
        return []

    # Inline images — drop failures, never block the article
    verified = [images[0]]
    for idx, img in enumerate(images[1:], start=1):
        if _check_one_image(img, article_data, role='inline', image_index=idx):
            verified.append(img)
        else:
            log.warning(
                "Inline image idx=%d (provider=%s, tier=%s) failed vision check — dropped.",
                idx, img.get('provider', '?'), img.get('evidenceTier', '?'),
            )

    return verified


def _get_editorial_provider():
    global _editorial_provider
    if _editorial_provider is None:
        from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, LORD_VOICE
        from providers.base import EditorialStandard
        from providers.impl.claude_editorial import ClaudeEditorialProvider
        lord_standard = EditorialStandard(
            publication_name='LORD',
            voice_prompt=LORD_VOICE,
        )
        _editorial_provider = ClaudeEditorialProvider(
            api_key=ANTHROPIC_API_KEY,
            model=ANTHROPIC_MODEL,
            editorial_standard=lord_standard,
        )
    return _editorial_provider


def _run_editorial_review(article_data: dict) -> bool:
    """Run editorial review gate if enabled. Returns False to abort on FAIL."""
    if not QUALITY_EDITORIAL_REVIEW:
        return True

    provider = _get_editorial_provider()
    result = provider.review(article_data)

    fail_issues = [i for i in result.issues if i.severity == 'FAIL']
    warn_issues = [i for i in result.issues if i.severity == 'WARN']
    info_issues = [i for i in result.issues if i.severity == 'INFO']

    for issue in info_issues:
        log.info("EDITORIAL INFO [%s]: %s", issue.category, issue.description)
    for issue in warn_issues:
        log.warning("EDITORIAL WARN [%s]: %s", issue.category, issue.description)

    log.info(
        "EDITORIAL REVIEW: %s (confidence: %.2f, FAIL=%d, WARN=%d, INFO=%d) — %s",
        result.result, result.confidence,
        len(fail_issues), len(warn_issues), len(info_issues),
        result.summary[:100] if result.summary else '',
    )

    if result.result == 'FAIL':
        for issue in fail_issues:
            log.error("EDITORIAL FAIL [%s]: %s", issue.category, issue.description)
        log.error(
            "Article '%s' failed editorial review — skipping.",
            article_data.get('title', '')[:60],
        )
        return False

    if result.result == 'UNCERTAIN':
        if QUALITY_EDITORIAL_FAIL_OPEN:
            log.warning(
                "Editorial review uncertain for '%s' — proceeding (fail-open mode).",
                article_data.get('title', '')[:60],
            )
        else:
            log.error(
                "Editorial review uncertain for '%s' — blocking (fail-closed, default). "
                "Set QUALITY_EDITORIAL_FAIL_OPEN=true to allow uncertain results through.",
                article_data.get('title', '')[:60],
            )
            return False

    return True


def _get_search_readiness_provider():
    global _search_readiness_provider
    if _search_readiness_provider is None:
        from providers.impl.local_search_readiness import LocalSearchReadinessProvider
        _search_readiness_provider = LocalSearchReadinessProvider()
    return _search_readiness_provider


def _run_search_readiness(article_data: dict, images: list) -> bool:
    """Run search readiness gate if enabled. Returns False to abort on FAIL."""
    if not QUALITY_SEO_VALIDATION:
        return True

    # Build check context with hero image metadata without mutating article_data
    # (image fields are formally attached by publish_article — we preview them here)
    check_data = dict(article_data)
    if images:
        hero = images[0]
        check_data['image']        = hero.get('url', '')
        check_data['imageAlt']     = hero.get('altText', '')
        check_data['inlineImages'] = images[1:]
    else:
        check_data.setdefault('image', '')
        check_data.setdefault('imageAlt', '')
        check_data['inlineImages'] = []

    provider = _get_search_readiness_provider()
    result   = provider.evaluate(check_data)

    fail_issues = [i for i in result.issues if i.severity == 'FAIL']
    warn_issues = [i for i in result.issues if i.severity == 'WARN']
    info_issues = [i for i in result.issues if i.severity == 'INFO']

    for issue in info_issues:
        log.info("SEARCH INFO [%s]: %s", issue.category, issue.description)
    for issue in warn_issues:
        log.warning("SEARCH WARN [%s]: %s", issue.category, issue.description)

    log.info(
        "SEARCH READINESS: %s (FAIL=%d, WARN=%d, INFO=%d) — %s",
        result.result, len(fail_issues), len(warn_issues), len(info_issues),
        result.summary[:100] if result.summary else '',
    )

    if result.result == 'FAIL':
        for issue in fail_issues:
            log.error("SEARCH FAIL [%s]: %s", issue.category, issue.description)
        log.error(
            "Article '%s' failed search readiness — skipping.",
            article_data.get('title', '')[:60],
        )
        return False

    return True


def _run_fact_verification(article_data: dict) -> bool:
    """Run fact verification gate if enabled. Returns False to abort on FAIL."""
    if not QUALITY_FACT_VERIFICATION:
        return True
    if not GOOGLE_GEMINI_API_KEY:
        log.warning("QUALITY_FACT_VERIFICATION=true but GOOGLE_GEMINI_API_KEY not set — skipping gate.")
        return True

    provider = _get_fact_provider()
    result = provider.verify(article_data)

    for w in result.warnings:
        log.warning("FACT WARN: %s", w)

    src_summary = ', '.join(s.name for s in result.sources[:3]) or 'none'
    log.info("FACT VERIFICATION: %s (confidence: %.2f, sources: %s)",
             result.result, result.confidence, src_summary)

    if result.result == 'FAIL':
        for e in result.errors:
            log.error("FACT ERROR: %s", e)
        log.error(
            "Article '%s' failed fact verification — skipping.",
            article_data.get('title', '')[:60],
        )
        return False

    if result.result == 'UNCERTAIN':
        if QUALITY_FACT_FAIL_OPEN:
            log.warning(
                "Fact verification uncertain for '%s' — proceeding (fail-open mode).",
                article_data.get('title', '')[:60],
            )
        else:
            log.error(
                "Fact verification uncertain for '%s' — blocking (fail-closed, default). "
                "Set QUALITY_FACT_FAIL_OPEN=true to allow uncertain results through.",
                article_data.get('title', '')[:60],
            )
            return False

    return True


def _run_metadata_validation(article_data: dict) -> bool:
    """Run metadata gate if enabled. Returns False to abort the cycle on failure."""
    if not QUALITY_METADATA_VALIDATION:
        return True
    result = validate_metadata(article_data)
    for w in result['warnings']:
        log.warning("METADATA WARN: %s", w)
    if result['result'] == 'FAIL':
        for e in result['errors']:
            log.error("METADATA ERROR: %s", e)
        log.error(
            "Article '%s' failed metadata validation — skipping.",
            article_data.get('title', '')[:60],
        )
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

        if not _run_metadata_validation(article_data):
            return False
        if not _run_fact_verification(article_data):
            return False

        images = _source_images(article_data)
        if not images:
            log.warning("No editorial image found for '%s' — skipping publication.", article_data.get('title', '')[:60])
            return False

        images = _run_vision_verification(images, article_data)
        if not images:
            return False

        if not _run_editorial_review(article_data):
            return False

        if not _run_search_readiness(article_data, images):
            return False

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

        index = load_index()
        today_features = count_today_by_type(index, 'feature')
        log.info("Features published today: %d / %d", today_features, MAX_FEATURES_PER_DAY)
        if today_features >= MAX_FEATURES_PER_DAY:
            log.info("Daily feature limit reached — skipping.")
            return False

        log.info("Fetching music news for feature inspiration...")
        news_items = get_trending_music_news()
        log.info("Retrieved %d music news items", len(news_items))

        if not news_items:
            log.warning("No news items available — feature cycle aborted.")
            return False

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

        if not _run_metadata_validation(article_data):
            return False
        if not _run_fact_verification(article_data):
            return False

        # Skip if the same artist was featured within the last 7 days.
        # Only check the first tag (the artist name, per the writer schema).
        # Checking every tag would match shared genre labels like "indie-rock"
        # and falsely reject nearly every feature as a duplicate.
        tags = article_data.get('tags', [])
        artist_tag = tags[0] if tags else ''
        if artist_tag and is_artist_covered(artist_tag, index, days=7):
            log.info("Artist '%s' featured recently — skipping duplicate feature.", artist_tag)
            return False

        images = _source_images(article_data, 'musician portrait studio')
        if not images:
            log.warning("No editorial image found for '%s' — skipping publication.", article_data.get('title', '')[:60])
            return False

        images = _run_vision_verification(images, article_data)
        if not images:
            return False

        if not _run_editorial_review(article_data):
            return False

        if not _run_search_readiness(article_data, images):
            return False

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
        today_reviews = count_today_by_type(index, 'review')
        log.info("Reviews published today: %d / %d", today_reviews, MAX_REVIEWS_PER_DAY)
        if today_reviews >= MAX_REVIEWS_PER_DAY:
            log.info("Daily review limit reached — skipping.")
            return False

        reviewed = _get_reviewed_albums(index)
        log.info("Albums already reviewed: %d", len(reviewed))

        log.info("Identifying current album from news...")
        album_info = extract_album_from_news(news_items, reviewed=reviewed)

        if not album_info:
            log.warning("Could not identify a current album from news — review cycle aborted.")
            return False

        if is_artist_covered(album_info['artist'], index):
            log.info("Artist '%s' already covered recently — skipping review.", album_info['artist'])
            return False

        log.info("Writing review: %s — %s", album_info['artist'], album_info['album'])
        article_data = write_review(album_info)
        log.info("Written: %s [%s]", article_data.get('title', '')[:60], article_data.get('rating', ''))

        if not _run_metadata_validation(article_data):
            return False
        if not _run_fact_verification(article_data):
            return False

        images = _source_images(article_data, 'vinyl record music studio')
        if not images:
            log.warning("No editorial image found for '%s' — skipping publication.", article_data.get('title', '')[:60])
            return False

        images = _run_vision_verification(images, article_data)
        if not images:
            return False

        if not _run_editorial_review(article_data):
            return False

        if not _run_search_readiness(article_data, images):
            return False

        entry = publish_article(article_data, images)
        log.info("Published review: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        return True

    except Exception as exc:
        log.error("Review cycle failed: %s", exc, exc_info=True)
        return False


def classic_review_cycle(target_artist: str = '', target_album: str = '') -> bool:
    """Execute one classic album (historical reassessment) review cycle.

    target_artist / target_album: when both are non-empty, bypass automatic
    album selection and use the supplied values. Intended for Golden Article
    validation runs and deterministic regression testing.
    """
    global _classic_attempted
    using_target = bool(target_artist and target_album)
    album_info: dict | None = None
    published = False

    log.info("─── Classic Review cycle starting ─────────────────────────")
    try:
        if not _check_api_key():
            return False

        index = load_index()
        reviewed = _get_reviewed_albums(index)
        log.info("Albums already reviewed: %d", len(reviewed))

        if using_target:
            album_info = {
                'artist': target_artist,
                'album': target_album,
                'year': '',
                'context': f'Golden Article validation: {target_artist} — {target_album}',
                'imageQuery': f'{target_artist} musician portrait',
            }
            log.info("─── GOLDEN ARTICLE TARGET ──────────────────────────────────")
            log.info("  Artist: %s", target_artist)
            log.info("  Album:  %s", target_album)
            log.info("────────────────────────────────────────────────────────────")
        else:
            log.info("Selecting classic album for reassessment...")
            album_info = pick_classic_album(reviewed, attempted=_classic_attempted)
            log.info("Selected: %s — %s (%s)", album_info['artist'], album_info['album'], album_info.get('year', ''))

        # Hard duplicate guard — exits before any API calls are made.
        # For target overrides (Golden Article / QA), log a warning and continue
        # since the run is intentionally forced for validation.
        if is_already_reviewed(album_info, reviewed):
            if using_target:
                log.warning(
                    "Duplicate guard (bypassed — target override): %s — %s was already reviewed.",
                    album_info.get('artist'), album_info.get('album'),
                )
            else:
                log.info(
                    "Duplicate guard: %s — %s already reviewed — skipping.",
                    album_info.get('artist'), album_info.get('album'),
                )
                return False

        article_data = write_classic_review(album_info)
        log.info("Written: %s [%s]", article_data.get('title', '')[:60], article_data.get('rating', ''))

        if not _run_metadata_validation(article_data):
            return False
        if not _run_fact_verification(article_data):
            return False

        images = _source_images(article_data, 'vintage vinyl record collection')
        if not images:
            log.warning("No editorial image found for '%s' — skipping publication.", article_data.get('title', '')[:60])
            return False

        images = _run_vision_verification(images, article_data)
        if not images:
            return False

        if not _run_editorial_review(article_data):
            return False

        if not _run_search_readiness(article_data, images):
            return False

        entry = publish_article(article_data, images)
        log.info("Published classic review: %s", entry['url'])
        log.info("──────────────────────────────────────────────────────────")
        published = True
        return True

    except Exception as exc:
        log.error("Classic review cycle failed: %s", exc, exc_info=True)
        return False

    finally:
        # Track failed non-target selections so daemon mode doesn't immediately
        # re-select the same candidate on the next scheduling tick.
        if album_info and not using_target and not published:
            _classic_attempted.append(f"{album_info['artist']} — {album_info['album']}")


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
    parser.add_argument(
        '--target-artist',
        default='',
        help='Force a specific artist for classic-review (Golden Article / QA)',
    )
    parser.add_argument(
        '--target-album',
        default='',
        help='Force a specific album for classic-review (Golden Article / QA)',
    )
    args = parser.parse_args()

    if args.run_now:
        dispatch = {
            'bulletin':       run_cycle,
            'feature':        feature_cycle,
            'review':         review_cycle,
            'classic-review': lambda: classic_review_cycle(
                target_artist=args.target_artist,
                target_album=args.target_album,
            ),
        }
        dispatch[args.type]()
        sys.exit(0)  # Always exit 0 — never fail the CI step
    else:
        run_daemon()


if __name__ == '__main__':
    main()

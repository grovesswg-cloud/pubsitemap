"""Search Readiness Provider — structural and technical publication quality.

Evaluates each article for technical excellence, machine-readability, and
discoverability. This is not SEO optimisation — it is publication quality.

Philosophy: Optimize for understanding, not manipulation. A technically excellent
article naturally satisfies the vast majority of modern search requirements without
keyword density hacks or algorithmic gaming.

Checks performed (no AI, no external API — all deterministic):
  - Title quality (length, presence)
  - Meta description / deck (presence, length)
  - Heading hierarchy (H1 in body, skipped levels)
  - Open Graph completeness (og:image availability)
  - Image metadata (alt text presence and quality)
  - Structured data fields (NewsArticle schema prerequisites)
  - Slug quality (derived from title)
  - Internal linking (informational only)
  - Duplicate metadata (title == description)

Swap this file to use an AI-assisted or external-API implementation.
"""
import logging
import re

from providers.base import SearchReadinessProvider, SearchReadinessResult, SearchReadinessIssue

log = logging.getLogger('lord.search_readiness')

_H1_RE          = re.compile(r'<h1[\s>]', re.IGNORECASE)
_H2_RE          = re.compile(r'<h2[\s>]', re.IGNORECASE)
_H3_RE          = re.compile(r'<h3[\s>]', re.IGNORECASE)
_INTERNAL_RE    = re.compile(r'href=["\'](?:\.\./|/)', re.IGNORECASE)
_IMG_EMPTY_ALT  = re.compile(r'<img[^>]+alt=["\']["\']', re.IGNORECASE)
_IMG_NO_ALT     = re.compile(r'<img(?![^>]*\balt\b)[^>]*/?>',  re.IGNORECASE)
_SLUG_CLEAN_RE  = re.compile(r'[^\w\s-]')
_SLUG_SPACE_RE  = re.compile(r'[\s_]+')

_GENERIC_ALT = {'image', 'photo', 'picture', 'img', 'figure', 'thumbnail', 'hero', 'untitled'}


def _derive_slug(title: str) -> str:
    s = _SLUG_CLEAN_RE.sub('', title.lower()).strip()
    s = _SLUG_SPACE_RE.sub('-', s)
    return re.sub(r'-{2,}', '-', s).strip('-')[:80]


class LocalSearchReadinessProvider(SearchReadinessProvider):
    """Deterministic, dependency-free search readiness evaluator."""

    def evaluate(self, article_data: dict) -> SearchReadinessResult:
        issues: list[SearchReadinessIssue] = []

        title      = (article_data.get('title')    or '').strip()
        deck       = (article_data.get('deck')     or '').strip()
        body       = (article_data.get('body')     or '').strip()
        date       = (article_data.get('date')     or '').strip()
        image_url  = (article_data.get('image')    or '').strip()
        image_alt  = (article_data.get('imageAlt') or '').strip()

        # ── Title ──────────────────────────────────────────────────────────────
        if not title:
            issues.append(SearchReadinessIssue(
                severity='FAIL',
                category='title',
                description='Article title is missing.',
                recommendation='Every article must have a title.',
            ))
        else:
            if len(title) < 10:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='title',
                    description=f'Title is very short ({len(title)} chars) — may not display well in search results.',
                    recommendation='Aim for 30–60 characters.',
                ))
            if len(title) > 70:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='title',
                    description=f'Title is {len(title)} chars — will be truncated by search engines.',
                    recommendation='Keep titles under 60–70 characters to avoid truncation.',
                ))

        # ── Meta description (deck) ────────────────────────────────────────────
        if not deck:
            issues.append(SearchReadinessIssue(
                severity='WARN',
                category='meta_description',
                description='Meta description (deck) is missing — search snippets will be auto-generated.',
                recommendation='A descriptive deck improves search result click-through rates.',
            ))
        else:
            if len(deck) < 50:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='meta_description',
                    description=f'Meta description is short ({len(deck)} chars).',
                    recommendation='Aim for 120–160 characters for an effective meta description.',
                ))
            if len(deck) > 160:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='meta_description',
                    description=f'Meta description is {len(deck)} chars — will be truncated in search results.',
                    recommendation='Keep meta descriptions under 160 characters.',
                ))

        # ── Duplicate metadata ─────────────────────────────────────────────────
        if title and deck and title.lower() == deck.lower():
            issues.append(SearchReadinessIssue(
                severity='WARN',
                category='duplicate_metadata',
                description='Title and meta description are identical.',
                recommendation='The deck should expand on the title, not repeat it.',
            ))

        # ── Heading hierarchy ──────────────────────────────────────────────────
        if body:
            h1_count = len(_H1_RE.findall(body))
            if h1_count > 0:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='headings',
                    description=(
                        f'Body contains {h1_count} H1 tag(s). '
                        'The article title is the page H1 — body sections should use H2/H3.'
                    ),
                    recommendation='Replace H1 tags in the article body with H2 or H3.',
                ))

            has_h3 = bool(_H3_RE.search(body))
            has_h2 = bool(_H2_RE.search(body))
            if has_h3 and not has_h2:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='headings',
                    description='Body uses H3 headings without any H2 headings — heading level skipped.',
                    recommendation='Introduce H2 section headings before using H3 sub-headings.',
                ))

        # ── Open Graph ─────────────────────────────────────────────────────────
        if not image_url:
            issues.append(SearchReadinessIssue(
                severity='WARN',
                category='open_graph',
                description='No hero image — og:image will be absent, degrading social sharing previews.',
                recommendation='All articles should have a hero image.',
            ))

        # ── Image metadata (accessibility + discoverability) ───────────────────
        if image_url:
            if not image_alt:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='image_metadata',
                    description='Hero image is missing alt text.',
                    recommendation='Describe the image — include the artist name and context.',
                ))
            elif image_alt.lower().strip() in _GENERIC_ALT:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='image_metadata',
                    description=f'Hero image alt text is generic: "{image_alt}".',
                    recommendation='Describe what the image shows, including the artist name and context.',
                ))

        if body:
            bad_alts = len(_IMG_EMPTY_ALT.findall(body)) + len(_IMG_NO_ALT.findall(body))
            if bad_alts:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='image_metadata',
                    description=f'{bad_alts} inline image(s) have missing or empty alt text.',
                    recommendation='Every image must have descriptive alt text for accessibility and image search.',
                ))

        # ── Structured data prerequisites (NewsArticle) ────────────────────────
        if not date:
            issues.append(SearchReadinessIssue(
                severity='WARN',
                category='structured_data',
                description='Publication date is missing — required for NewsArticle structured data.',
                recommendation='All articles must have a publication date.',
            ))

        # ── Slug quality ───────────────────────────────────────────────────────
        if title:
            slug = _derive_slug(title)
            if len(slug) < 5:
                issues.append(SearchReadinessIssue(
                    severity='WARN',
                    category='slug',
                    description='Article title produces a very short URL slug.',
                    recommendation='Use a descriptive title so the URL is readable and meaningful.',
                ))

        # ── Internal links (informational) ─────────────────────────────────────
        if body and not _INTERNAL_RE.search(body):
            issues.append(SearchReadinessIssue(
                severity='INFO',
                category='internal_links',
                description='No internal links detected in the article body.',
                recommendation='Consider linking to related articles to improve site discoverability.',
            ))

        # ── Result ─────────────────────────────────────────────────────────────
        has_fail = any(i.severity == 'FAIL' for i in issues)
        result   = 'FAIL' if has_fail else 'PASS'

        fail_n = sum(1 for i in issues if i.severity == 'FAIL')
        warn_n = sum(1 for i in issues if i.severity == 'WARN')
        info_n = sum(1 for i in issues if i.severity == 'INFO')

        if not issues:
            summary = 'Article meets all search readiness requirements.'
        elif has_fail:
            summary = f'{fail_n} blocking issue(s), {warn_n} warning(s). Publication blocked.'
        else:
            summary = f'{warn_n} warning(s), {info_n} note(s). Publication not blocked.'

        return SearchReadinessResult(result=result, issues=issues, summary=summary)

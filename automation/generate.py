#!/usr/bin/env python3
"""LORD Editorial Calibration — Article Generator

Generates articles through the full editorial pipeline (reasoning → write → revision)
without publishing. Every run saves a complete audit trail to calibration/<run-folder>/.

Usage:
  python generate.py review --artist "Kendrick Lamar" --album "GNX"
  python generate.py classic-review --artist "Massive Attack" --album "Mezzanine" --year 1998
  python generate.py feature --title "Massive Attack Announce New Album" --summary "..."
  python generate.py bulletin --title "Massive Attack Announce New Tour"

  # Bypass flags (for comparison runs)
  python generate.py review --artist "..." --album "..." --no-engine
  python generate.py review --artist "..." --album "..." --no-revision

  # Tag runs for grouping
  python generate.py review --artist "..." --album "..." --tag sprint-1

Output (one folder per run):
  calibration/2026-06-27-1430--kendrick-lamar-gnx-review/
    summary.md     ← open this first (full editorial digest)
    article.html   ← final article in browser
    writer.html    ← pre-revision draft (when revision ran)
    article.json   ← full article dict
    brief.json     ← ReasoningBrief (when engine ran)
    revision.json  ← RevisionReport (when revision ran)
    run.json       ← run metadata (git commit, model, flags)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from config import ANTHROPIC_MODEL, REASONING_ENGINE, REVISION_ENGINE

ROOT_DIR = Path(__file__).parent.parent
CALIBRATION_DIR = ROOT_DIR / 'calibration'


# ─── Utilities ────────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int = 40) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text[:max_len].rstrip('-')


def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=str(ROOT_DIR),
        )
        return result.stdout.strip()[:12] if result.returncode == 0 else ''
    except Exception:
        return ''


def _strip_html(html: str) -> str:
    text = re.sub(r'<[^>]+>', '', html or '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _make_run_dir(article_type: str, subject: dict, tag: str = '') -> Path:
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime('%Y-%m-%d-%H%M')
    artist = subject.get('artist', '')
    album = subject.get('album', '')
    title = subject.get('title', '')
    if artist and album:
        slug = _slugify(f'{artist}-{album}-{article_type}')
    elif title:
        slug = _slugify(f'{article_type}-{title}')
    else:
        slug = article_type
    name = f'{ts}--{slug}'
    if tag:
        name = f'{name}--{_slugify(tag)}'
    path = CALIBRATION_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_articles_index() -> dict:
    from config import ARTICLES_JSON
    try:
        with open(ARTICLES_JSON, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'articles': []}


# ─── HTML rendering ───────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 740px; margin: 48px auto; padding: 0 24px; line-height: 1.8; color: #1a1a1a; }}
  h1 {{ font-size: 1.65em; line-height: 1.3; margin: 0 0 0.3em; }}
  .deck {{ font-size: 1.1em; color: #444; margin: 0 0 0.6em; font-style: italic; }}
  .meta {{ font-size: 0.82em; color: #888; margin-bottom: 2.5em; }}
  .label {{ background: #f0f0f0; padding: 2px 8px; border-radius: 3px; margin-right: 5px; font-style: normal; }}
  .rating {{ background: #1a1a1a; color: #fff; padding: 2px 8px; border-radius: 3px; margin-right: 5px; }}
  p {{ margin: 0 0 1.3em; }}
  em {{ font-style: italic; }}
  .banner {{ background: #fff8e1; border-left: 3px solid #f9a825; padding: 8px 14px; font-size: 0.85em; margin-bottom: 2em; color: #555; }}
</style>
</head>
<body>
{banner}
<p class="meta">
  <span class="label">{type_label}</span>{rating_tag}<span>{meta_extra}</span>
</p>
<h1>{title}</h1>
{deck_html}
{body}
</body>
</html>
"""


def _render_html(article_data: dict, stage: str = 'final') -> str:
    if stage == 'writer':
        banner = '<div class="banner">Writer draft — pre-revision. Compare with article.html to see what the Revision Engine changed.</div>'
    else:
        banner = ''
    title = article_data.get('title', '(untitled)')
    deck = article_data.get('deck', '')
    deck_html = f'<p class="deck">{deck}</p>' if deck else ''
    body = article_data.get('body', '')
    type_label = article_data.get('type', '').upper()
    rating = article_data.get('rating', '')
    rating_tag = f'<span class="rating">{rating}</span>' if rating else ''
    artist = article_data.get('artistName', '')
    album = article_data.get('albumName', '')
    if artist and album:
        meta_extra = f'{artist} — {album}'
    else:
        meta_extra = article_data.get('source', '')
    return _HTML_TEMPLATE.format(
        title=title, deck_html=deck_html, body=body,
        type_label=type_label, rating_tag=rating_tag, meta_extra=meta_extra,
        banner=banner,
    )


# ─── summary.md ───────────────────────────────────────────────────────────────

def _make_summary(
    article_type: str,
    subject: dict,
    article_data: dict,
    brief,
    revision_report,
) -> str:
    lines = []

    artist = subject.get('artist', '')
    album = subject.get('album', '')
    title = article_data.get('title', '(untitled)')
    rating = article_data.get('rating', '')
    date = article_data.get('date', '')

    if artist and album:
        lines.append(f'# {article_type.upper()} — {artist}: {album}')
    else:
        lines.append(f'# {article_type.upper()} — {title}')

    meta = [f'Date: {date}']
    if rating:
        meta.append(f'Rating: **{rating}**')
    if brief:
        meta.append(f'Confidence: {brief.confidence}')
        meta.append(f'Thesis confidence: {brief.thesis_confidence}')
    lines.append('  '.join(meta))
    lines.append('')

    # Brief
    if brief:
        lines.append('## THESIS')
        lines.append(brief.thesis)
        lines.append('')

        if brief.rejected_theses:
            lines.append('## REJECTED THESES')
            for t in brief.rejected_theses:
                lines.append(f'- {t}')
            lines.append('')

        if brief.counterargument:
            lines.append('## COUNTERARGUMENT CONSIDERED')
            lines.append(brief.counterargument)
            lines.append('')

        if brief.evidence:
            lines.append('## EVIDENCE MAP')
            for e in brief.evidence:
                id_tag = f'{e.id} ' if e.id else ''
                lines.append(f'- {id_tag}[{e.confidence.upper()}] {e.observation}')
                lines.append(f'  → {e.evidence}')
                lines.append(f'  → supports: {e.supports}')
            lines.append('')

        if brief.weaknesses:
            lines.append('## WEAKNESSES (mandatory in article)')
            for w in brief.weaknesses:
                lines.append(f'- {w}')
            lines.append('')

        if brief.editor_notes:
            lines.append('## EDITOR NOTES')
            for n in brief.editor_notes:
                lines.append(f'- {n}')
            lines.append('')

    # Revision report
    if revision_report:
        n_fid = len(revision_report.fidelity_notes())
        n_craft = len(revision_report.craft_notes())
        n_total = len(revision_report.notes)
        n_rewritten = len(revision_report.revised_paragraphs)

        lines.append(f'## CRITIQUE ({n_total} note{"s" if n_total != 1 else ""}: {n_fid} fidelity, {n_craft} craft)')
        if revision_report.notes:
            for note in revision_report.notes:
                para = f'¶{note.paragraph}' if note.paragraph > 0 else '(whole-draft)'
                selected_mark = '✓ SELECTED' if note.id in revision_report.plan else '· skipped'
                lines.append(f'**{note.id}** [{note.impact.upper()} · {note.layer} · {note.issue_type}] {para}  {selected_mark}')
                lines.append(note.description)
                lines.append(f'→ fix: {note.fix}')
                lines.append('')
        else:
            lines.append('No issues found — draft published as written.')
            lines.append('')

        lines.append('## REVISION PLAN')
        if revision_report.plan:
            touched = sorted({n.paragraph for n in revision_report.selected_notes() if n.paragraph > 0})
            lines.append(f'Paragraphs rewritten: {", ".join(str(i) for i in touched)} ({n_rewritten} total)')
            not_selected = [n.id for n in revision_report.notes if n.id not in revision_report.plan]
            if not_selected:
                lines.append(f'Not selected (LOW impact or beyond cap): {", ".join(not_selected)}')
        else:
            lines.append('No edits — draft published as written.')
        lines.append('')

    # Article body
    lines.append('---')
    lines.append('')
    lines.append('## ARTICLE')
    lines.append('')
    lines.append(f'**{title}**')
    if article_data.get('deck'):
        lines.append(f'*{article_data["deck"]}*')
    lines.append('')
    lines.append(_strip_html(article_data.get('body', '')))

    return '\n'.join(lines)


# ─── Artifact saving ──────────────────────────────────────────────────────────

def _save_artifacts(
    run_dir: Path,
    article_type: str,
    subject: dict,
    article_data: dict,
    brief,
    revision_report,
    pre_revision_body: str,
    use_engine: bool,
    use_revision: bool,
    tag: str,
) -> None:
    # run.json — reproducibility record
    run_meta = {
        'article_type': article_type,
        'generated_at': datetime.now(tz=timezone.utc).isoformat(),
        'git_commit': _get_git_commit(),
        'model': ANTHROPIC_MODEL,
        'engine': use_engine,
        'revision': use_revision,
        'tag': tag,
        'subject': {k: v for k, v in subject.items() if not k.startswith('_')},
        'result': {
            'title': article_data.get('title', ''),
            'rating': article_data.get('rating', ''),
            'confidence': getattr(brief, 'confidence', None),
            'thesis_confidence': getattr(brief, 'thesis_confidence', None),
            'revised': getattr(revision_report, 'revised', None),
            'paragraphs_rewritten': len(getattr(revision_report, 'revised_paragraphs', {})),
        },
    }
    (run_dir / 'run.json').write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False), encoding='utf-8')

    # article.json
    (run_dir / 'article.json').write_text(
        json.dumps(article_data, indent=2, ensure_ascii=False), encoding='utf-8')

    # brief.json
    if brief is not None:
        (run_dir / 'brief.json').write_text(brief.to_json(), encoding='utf-8')

    # revision.json
    if revision_report is not None:
        (run_dir / 'revision.json').write_text(revision_report.to_json(), encoding='utf-8')

    # writer.html — pre-revision draft (only when revision ran)
    if revision_report is not None and pre_revision_body:
        pre_data = {**article_data, 'body': pre_revision_body}
        (run_dir / 'writer.html').write_text(
            _render_html(pre_data, stage='writer'), encoding='utf-8')

    # article.html — final output
    (run_dir / 'article.html').write_text(
        _render_html(article_data, stage='final'), encoding='utf-8')

    # summary.md — full editorial digest
    (run_dir / 'summary.md').write_text(
        _make_summary(article_type, subject, article_data, brief, revision_report),
        encoding='utf-8',
    )


# ─── Pipeline stages ──────────────────────────────────────────────────────────

def _run_reasoning(subject: dict, article_type: str, use_engine: bool):
    if not use_engine:
        print('  [engine] skipped (--no-engine)')
        return None
    from reasoning import run as engine_run
    from editorial import load_criticism_context
    index = _load_articles_index()
    print(f'  [engine] running ({article_type})...')
    brief = engine_run(
        subject=subject,
        editorial_context=load_criticism_context(),
        articles_index=index,
        article_type=article_type,
    )
    print(f'  [engine] done — confidence={brief.confidence}, thesis_confidence={brief.thesis_confidence}')
    return brief


def _run_revision(article_data: dict, brief, article_type: str, use_revision: bool):
    if not use_revision:
        print('  [revision] skipped (--no-revision)')
        return None
    from revision import run as revision_run
    from editorial import load_criticism_context
    print('  [revision] running...')
    report = revision_run(
        draft=article_data,
        brief=brief,
        editorial_context=load_criticism_context(),
        article_type=article_type,
    )
    n_rewritten = len(report.revised_paragraphs)
    print(f'  [revision] done — {report.summary()}')
    if report.revised:
        article_data['body'] = report.revised_body
        print(f'  [revision] applied {n_rewritten} targeted rewrite(s)')
    else:
        print('  [revision] draft published as written (no edits)')
    return report


def _print_done(run_dir: Path, article_data: dict) -> None:
    print(f'\n✓ Complete: {article_data.get("title", "")[:70]}')
    if article_data.get('rating'):
        print(f'  Rating: {article_data["rating"]}')
    print(f'\n  Files saved to: {run_dir.relative_to(ROOT_DIR)}')
    print(f'    summary.md   ← open this first')
    print(f'    article.html ← read in browser')
    if (run_dir / 'writer.html').exists():
        print(f'    writer.html  ← pre-revision draft (compare with article.html)')


# ─── Article type handlers ────────────────────────────────────────────────────

def generate_review(args) -> None:
    subject = {
        'artist': args.artist,
        'album': args.album,
        'context': getattr(args, 'context', '') or '',
    }
    use_engine = REASONING_ENGINE and not args.no_engine
    use_revision = REVISION_ENGINE and not args.no_revision

    run_dir = _make_run_dir('review', subject, tag=args.tag)
    print(f'\nGenerating REVIEW: {args.artist} — {args.album}')
    print(f'Flags: engine={use_engine}, revision={use_revision}')

    brief = _run_reasoning(subject, 'review', use_engine)

    from review_writer import write_review
    print('  [writer] writing review...')
    article_data = write_review(
        {'artist': args.artist, 'album': args.album, 'context': subject['context']},
        brief=brief,
    )
    print(f'  [writer] done — "{article_data.get("title", "")[:60]}" [{article_data.get("rating", "")}]')

    pre_revision_body = article_data.get('body', '')
    revision_report = _run_revision(article_data, brief, 'review', use_revision)

    _save_artifacts(run_dir, 'review', subject, article_data, brief, revision_report,
                    pre_revision_body, use_engine, use_revision, args.tag)
    _print_done(run_dir, article_data)


def generate_classic_review(args) -> None:
    subject = {
        'artist': args.artist,
        'album': args.album,
        'year': getattr(args, 'year', '') or '',
        'context': getattr(args, 'context', '') or '',
    }
    use_engine = REASONING_ENGINE and not args.no_engine
    use_revision = REVISION_ENGINE and not args.no_revision

    run_dir = _make_run_dir('classic-review', subject, tag=args.tag)
    year_str = f' ({subject["year"]})' if subject['year'] else ''
    print(f'\nGenerating CLASSIC REVIEW: {args.artist} — {args.album}{year_str}')
    print(f'Flags: engine={use_engine}, revision={use_revision}')

    brief = _run_reasoning(subject, 'review', use_engine)

    from review_writer import write_classic_review
    print('  [writer] writing classic review...')
    article_data = write_classic_review(subject, brief=brief)
    print(f'  [writer] done — "{article_data.get("title", "")[:60]}" [{article_data.get("rating", "")}]')

    pre_revision_body = article_data.get('body', '')
    revision_report = _run_revision(article_data, brief, 'review', use_revision)

    _save_artifacts(run_dir, 'classic-review', subject, article_data, brief, revision_report,
                    pre_revision_body, use_engine, use_revision, args.tag)
    _print_done(run_dir, article_data)


def generate_feature(args) -> None:
    subject = {
        'title': args.title,
        'summary': getattr(args, 'summary', '') or '',
        'source': '',
        'link': '',
    }
    use_engine = REASONING_ENGINE and not args.no_engine
    use_revision = REVISION_ENGINE and not args.no_revision

    run_dir = _make_run_dir('feature', subject, tag=args.tag)
    print(f'\nGenerating FEATURE: {args.title[:70]}')
    print(f'Flags: engine={use_engine}, revision={use_revision}')

    brief = _run_reasoning(subject, 'feature-context', use_engine)

    from feature_writer import write_feature
    print('  [writer] writing feature...')
    article_data = write_feature(subject, brief=brief)
    print(f'  [writer] done — "{article_data.get("title", "")[:60]}"')

    pre_revision_body = article_data.get('body', '')
    revision_report = _run_revision(article_data, brief, 'feature', use_revision)

    _save_artifacts(run_dir, 'feature', subject, article_data, brief, revision_report,
                    pre_revision_body, use_engine, use_revision, args.tag)
    _print_done(run_dir, article_data)


def generate_bulletin(args) -> None:
    subject = {
        'title': args.title,
        'summary': getattr(args, 'summary', '') or '',
        'source': '',
        'link': '',
    }
    run_dir = _make_run_dir('bulletin', subject, tag=args.tag)
    print(f'\nGenerating BULLETIN: {args.title[:70]}')
    print('  [engine] skipped — bulletins are journalism, not criticism')
    print('  [revision] skipped — bulletins are journalism, not criticism')

    from article_writer import write_bulletin
    print('  [writer] writing bulletin...')
    article_data = write_bulletin(subject)
    print(f'  [writer] done — "{article_data.get("title", "")[:60]}"')

    _save_artifacts(run_dir, 'bulletin', subject, article_data, None, None,
                    '', False, False, args.tag)
    _print_done(run_dir, article_data)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument('--tag', default='', help='Tag for grouping calibration runs (e.g. sprint-1)')
    p.add_argument('--no-engine', action='store_true', dest='no_engine',
                   help='Bypass the reasoning engine (craft critique only)')
    p.add_argument('--no-revision', action='store_true', dest='no_revision',
                   help='Bypass the revision engine (publish writer draft as-is)')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='LORD Editorial Calibration — generate articles without publishing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest='type', required=True, metavar='TYPE')

    p_review = sub.add_parser('review', help='Current album review')
    p_review.add_argument('--artist', required=True)
    p_review.add_argument('--album', required=True)
    p_review.add_argument('--context', default='', help='Optional context / news hook')
    _add_common_args(p_review)

    p_classic = sub.add_parser('classic-review', help='Classic album reassessment (10+ years old)')
    p_classic.add_argument('--artist', required=True)
    p_classic.add_argument('--album', required=True)
    p_classic.add_argument('--year', default='', help='Year of original release')
    p_classic.add_argument('--context', default='', help='Optional context / why reassess now')
    _add_common_args(p_classic)

    p_feature = sub.add_parser('feature', help='Long-form editorial feature')
    p_feature.add_argument('--title', required=True, help='News headline used as launching point')
    p_feature.add_argument('--summary', default='', help='Context for the feature (recommended)')
    _add_common_args(p_feature)

    p_bulletin = sub.add_parser('bulletin', help='News bulletin (journalism pipeline only)')
    p_bulletin.add_argument('--title', required=True, help='News headline')
    p_bulletin.add_argument('--summary', default='', help='Brief news context')
    _add_common_args(p_bulletin)

    args = parser.parse_args()
    dispatch = {
        'review':         generate_review,
        'classic-review': generate_classic_review,
        'feature':        generate_feature,
        'bulletin':       generate_bulletin,
    }
    try:
        dispatch[args.type](args)
    except KeyboardInterrupt:
        print('\nAborted.')
        sys.exit(1)
    except Exception as exc:
        print(f'\nError: {exc}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

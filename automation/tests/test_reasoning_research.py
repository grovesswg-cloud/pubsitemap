"""Tests for the Research stage (publication memory + positioning stubs)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from reasoning.stages.research import run, _build_publication_memory, _build_positioning


_SAMPLE_INDEX = {
    'articles': [
        {
            'type': 'bulletin',
            'title': 'Massive Attack Announce New Project',
            'date': '2025-03-01',
            'tags': ['massive-attack', 'electronic'],
            'artistName': 'Massive Attack',
            'albumName': '',
            'rating': '',
        },
        {
            'type': 'review',
            'title': "Mezzanine at Twenty-Six",
            'date': '2026-06-26',
            'tags': ['massive-attack', 'mezzanine', 'electronic'],
            'artistName': 'Massive Attack',
            'albumName': 'Mezzanine',
            'rating': 'Eternal',
        },
        {
            'type': 'bulletin',
            'title': 'Radiohead Release Archival Material',
            'date': '2025-11-10',
            'tags': ['radiohead', 'rock'],
            'artistName': 'Radiohead',
            'albumName': '',
            'rating': '',
        },
    ]
}


def test_publication_memory_finds_prior_coverage():
    subject = {'artist': 'Massive Attack', 'album': 'Mezzanine'}
    mem = _build_publication_memory(subject, _SAMPLE_INDEX)
    assert mem['coverage_count'] == 2
    assert len(mem['prior_coverage']) == 2


def test_publication_memory_no_match():
    subject = {'artist': 'Portishead', 'album': 'Dummy'}
    mem = _build_publication_memory(subject, _SAMPLE_INDEX)
    assert mem['coverage_count'] == 0
    assert mem['prior_coverage'] == []


def test_publication_memory_captures_rating():
    subject = {'artist': 'Massive Attack', 'album': 'Mezzanine'}
    mem = _build_publication_memory(subject, _SAMPLE_INDEX)
    ratings = mem['previous_ratings']
    assert len(ratings) == 1
    assert ratings[0]['rating'] == 'Eternal'
    assert ratings[0]['album'] == 'Mezzanine'


def test_publication_memory_case_insensitive():
    subject = {'artist': 'massive attack', 'album': 'mezzanine'}
    mem = _build_publication_memory(subject, _SAMPLE_INDEX)
    assert mem['coverage_count'] == 2


def test_publication_memory_empty_index():
    subject = {'artist': 'Massive Attack', 'album': 'Mezzanine'}
    mem = _build_publication_memory(subject, {'articles': []})
    assert mem['coverage_count'] == 0


def test_positioning_with_summary():
    subject = {
        'artist': 'Radiohead',
        'album': 'OK Computer',
        'summary': 'Critics have praised the album for its paranoid atmosphere and innovative production.',
    }
    pos = _build_positioning(subject)
    assert 'consensus' in pos
    assert 'underexplored' in pos
    assert len(pos['consensus']) > 0
    assert 'paranoid' in pos['consensus']


def test_positioning_without_summary_uses_title():
    subject = {'title': 'Radiohead Reissue Sells Out', 'artist': 'Radiohead'}
    pos = _build_positioning(subject)
    assert 'Radiohead' in pos['consensus']


def test_positioning_empty_subject():
    pos = _build_positioning({})
    assert pos['consensus'] == ''
    assert pos['underexplored'] == ''


def test_run_returns_both_dicts():
    subject = {'artist': 'Massive Attack', 'album': 'Mezzanine'}
    pub_mem, positioning = run(subject, _SAMPLE_INDEX)
    assert isinstance(pub_mem, dict)
    assert isinstance(positioning, dict)
    assert 'prior_coverage' in pub_mem
    assert 'consensus' in positioning

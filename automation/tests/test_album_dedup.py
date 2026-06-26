"""Tests for album duplicate detection: _normalize, _get_reviewed_albums, is_already_reviewed."""
import pytest
from album_finder import _normalize, _get_reviewed_albums, is_already_reviewed


# ─── _normalize ──────────────────────────────────────────────────────────────

def test_normalize_lowercases():
    assert _normalize("Massive Attack") == "massive attack"


def test_normalize_trims_whitespace():
    assert _normalize("  Mezzanine  ") == "mezzanine"


def test_normalize_collapses_spaces():
    assert _normalize("Massive  Attack") == "massive attack"


def test_normalize_unicode_nfkd():
    # Smart quotes and accents should survive comparison
    assert _normalize("Björk") == _normalize("Björk")


def test_normalize_casefold_handles_eszett():
    assert _normalize("STRASSE") == _normalize("Straße")


# ─── _get_reviewed_albums ─────────────────────────────────────────────────────

def _make_index(*articles):
    return {'articles': list(articles)}


def test_get_reviewed_albums_extracts_artist_and_album():
    index = _make_index({'type': 'review', 'artistName': 'Massive Attack', 'albumName': 'Mezzanine'})
    result = _get_reviewed_albums(index)
    assert result == [{'artist': 'Massive Attack', 'album': 'Mezzanine'}]


def test_get_reviewed_albums_includes_classic_review_type():
    index = _make_index({'type': 'classic-review', 'artistName': 'Portishead', 'albumName': 'Dummy'})
    result = _get_reviewed_albums(index)
    assert len(result) == 1


def test_get_reviewed_albums_excludes_bulletins():
    index = _make_index({'type': 'bulletin', 'artistName': 'Radiohead', 'albumName': 'OK Computer'})
    assert _get_reviewed_albums(index) == []


def test_get_reviewed_albums_excludes_features():
    index = _make_index({'type': 'feature', 'artistName': 'Radiohead', 'albumName': 'OK Computer'})
    assert _get_reviewed_albums(index) == []


def test_get_reviewed_albums_skips_entries_missing_both_fields():
    index = _make_index({'type': 'review', 'artistName': '', 'albumName': ''})
    assert _get_reviewed_albums(index) == []


def test_get_reviewed_albums_keeps_entries_with_only_artist():
    index = _make_index({'type': 'review', 'artistName': 'Solo Artist', 'albumName': ''})
    result = _get_reviewed_albums(index)
    assert result == [{'artist': 'Solo Artist', 'album': ''}]


def test_get_reviewed_albums_ignores_generated_title():
    index = _make_index({
        'type': 'review',
        'title': 'Mezzanine at Twenty-Five: The Album That Predicted the Dark',
        'artistName': 'Massive Attack',
        'albumName': 'Mezzanine',
    })
    result = _get_reviewed_albums(index)
    assert 'title' not in result[0]


# ─── is_already_reviewed ─────────────────────────────────────────────────────

_REVIEWED = [
    {'artist': 'Massive Attack', 'album': 'Mezzanine'},
    {'artist': 'Portishead', 'album': 'Dummy'},
]


def test_is_already_reviewed_exact_match():
    assert is_already_reviewed({'artist': 'Massive Attack', 'album': 'Mezzanine'}, _REVIEWED)


def test_is_already_reviewed_case_insensitive():
    assert is_already_reviewed({'artist': 'massive attack', 'album': 'MEZZANINE'}, _REVIEWED)


def test_is_already_reviewed_strips_whitespace():
    assert is_already_reviewed({'artist': '  Massive Attack  ', 'album': ' Mezzanine '}, _REVIEWED)


def test_is_already_reviewed_false_for_different_album():
    assert not is_already_reviewed({'artist': 'Massive Attack', 'album': 'Blue Lines'}, _REVIEWED)


def test_is_already_reviewed_false_for_different_artist():
    assert not is_already_reviewed({'artist': 'Tricky', 'album': 'Mezzanine'}, _REVIEWED)


def test_is_already_reviewed_false_for_empty_reviewed_list():
    assert not is_already_reviewed({'artist': 'Massive Attack', 'album': 'Mezzanine'}, [])


def test_is_already_reviewed_false_when_both_fields_empty():
    assert not is_already_reviewed({'artist': '', 'album': ''}, _REVIEWED)


def test_is_already_reviewed_unicode_normalization():
    reviewed = [{'artist': 'Björk', 'album': 'Homogenic'}]
    assert is_already_reviewed({'artist': 'Björk', 'album': 'Homogenic'}, reviewed)


def test_is_already_reviewed_different_title_same_album():
    """Core regression: different article title must not fool the guard."""
    reviewed = [{'artist': 'Massive Attack', 'album': 'Mezzanine'}]
    # Simulates a second Golden Article run that generated a different title
    album_info = {'artist': 'Massive Attack', 'album': 'Mezzanine'}
    assert is_already_reviewed(album_info, reviewed)

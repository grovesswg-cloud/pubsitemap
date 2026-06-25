"""Regression tests for entity identity verification in VisionVerificationProvider.

These tests guard against the class of failure where an image depicts a real entity
that SHARES A NAME with the article subject but is a DIFFERENT real-world entity.

Production failure that triggered this suite (2026-06-25):
  Article about Camille (French singer) published with inline image of
  Camille Claudel (French sculptor). Both are real people named Camille.
  The pipeline passed because it detected a real person — it did not
  verify that the person was the article's specific subject.

Each test in AMBIGUOUS_PAIRS corresponds to a known class of entity confusion.
When a new editorial failure is discovered, add it here permanently.
"""
import json
import unittest
from unittest.mock import MagicMock, patch


def _make_provider():
    with patch('google.generativeai.configure'), \
         patch('google.generativeai.GenerativeModel', return_value=MagicMock()):
        from providers.impl.gemini_vision import GeminiVisionProvider
        return GeminiVisionProvider(api_key='test-key')


def _response_json(
    *,
    entity_match: bool = True,
    expected_entity: str = 'Test Artist (musician)',
    detected_entity: str = 'Test Artist (musician)',
    entity_confidence: float = 0.97,
    mismatch_reason: str = '',
    person_match: bool = True,
    context_match: bool = True,
    technical_pass: bool = True,
    editorial_quality: str = 'adequate',
    result: str = 'PASS',
    confidence: float = 0.92,
) -> str:
    return json.dumps({
        'person_match': person_match,
        'person_match_confidence': 0.95,
        'context_match': context_match,
        'context_match_note': '',
        'technical_pass': technical_pass,
        'technical_notes': [],
        'editorial_quality': editorial_quality,
        'editorial_note': '',
        'entity_match': entity_match,
        'expected_entity': expected_entity,
        'detected_entity': detected_entity,
        'entity_confidence': entity_confidence,
        'mismatch_reason': mismatch_reason,
        'issues': [],
        'confidence': confidence,
        'result': result,
    })


# ---------------------------------------------------------------------------
# Known ambiguous entity pairs — expand when new editorial failures occur
# ---------------------------------------------------------------------------
AMBIGUOUS_PAIRS = [
    # (test_id, expected_entity, detected_entity, mismatch_reason)
    (
        'camille_singer_vs_claudel_sculptor',
        'Camille (French singer, born 1978)',
        'Camille Claudel (French sculptor, 1864–1943)',
        'Image depicts 19th-century sculptor, not contemporary singer',
    ),
    (
        'seal_musician_vs_animal',
        'Seal (British-Nigerian singer, born 1963)',
        'seal (marine animal, Phocidae)',
        'Image depicts a marine animal, not the recording artist',
    ),
    (
        'bush_band_vs_politician',
        'Bush (British rock band formed 1992)',
        'George W. Bush (43rd US President)',
        'Image depicts a politician, not the rock band',
    ),
    (
        'journey_band_vs_travel',
        'Journey (American rock band formed 1973)',
        'generic travel/road imagery (no people)',
        'Image depicts a journey/travel scene, not the rock band',
    ),
    (
        'america_band_vs_country',
        'America (British-American rock band formed 1970)',
        'United States of America (country, flag imagery)',
        'Image depicts Americana/national imagery, not the rock band',
    ),
    (
        'chicago_band_vs_city',
        'Chicago (American rock band formed 1967)',
        'Chicago, Illinois (city skyline)',
        'Image depicts the city, not the band',
    ),
    (
        'boston_band_vs_city',
        'Boston (American rock band formed 1976)',
        'Boston, Massachusetts (city)',
        'Image depicts the city, not the band',
    ),
    (
        'phoenix_band_vs_city',
        'Phoenix (French indie pop band formed 1995)',
        'Phoenix, Arizona (city)',
        'Image depicts the Arizona city, not the French band',
    ),
    (
        'queen_band_vs_royalty',
        'Queen (British rock band formed 1970)',
        'Queen Elizabeth II (British monarch)',
        'Image depicts royalty, not the rock band',
    ),
    (
        'eagles_band_vs_bird',
        'Eagles (American rock band formed 1971)',
        'bald eagle (Haliaeetus leucocephalus, bird)',
        'Image depicts a bird, not the rock band',
    ),
    (
        'garbage_band_vs_trash',
        'Garbage (Scottish-American rock band formed 1993)',
        'garbage/trash/waste (inanimate objects)',
        'Image depicts refuse, not the rock band',
    ),
    (
        'kiss_band_vs_kissing',
        'KISS (American rock band formed 1973)',
        'people kissing (generic romantic imagery)',
        'Image depicts a kiss/romantic gesture, not the rock band',
    ),
]


class TestEntityMatchPass(unittest.TestCase):
    """Correct entity → PASS."""

    def setUp(self):
        self.provider = _make_provider()

    def test_correct_entity_passes(self):
        result = self.provider._parse_response(_response_json(
            entity_match=True,
            expected_entity='Camille (French singer, born 1978)',
            detected_entity='Camille (French singer)',
        ))
        self.assertEqual(result.result, 'PASS')
        self.assertTrue(result.entity_match)
        self.assertEqual(result.expected_entity, 'Camille (French singer, born 1978)')
        self.assertEqual(result.detected_entity, 'Camille (French singer)')
        self.assertEqual(result.errors, [])

    def test_entity_match_fields_populated(self):
        result = self.provider._parse_response(_response_json(
            entity_match=True,
            entity_confidence=0.97,
        ))
        self.assertAlmostEqual(result.entity_confidence, 0.97)
        self.assertEqual(result.mismatch_reason, '')


class TestEntityMatchFail(unittest.TestCase):
    """Entity mismatch always → FAIL, regardless of model's result field."""

    def setUp(self):
        self.provider = _make_provider()

    def test_entity_mismatch_is_fail(self):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            expected_entity='Camille (French singer, born 1978)',
            detected_entity='Camille Claudel (French sculptor, 1864–1943)',
            mismatch_reason='Image depicts 19th-century sculptor, not contemporary singer',
            result='PASS',  # model says PASS — we must override to FAIL
        ))
        self.assertEqual(result.result, 'FAIL')
        self.assertFalse(result.entity_match)

    def test_entity_mismatch_model_already_says_fail(self):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            result='FAIL',
        ))
        self.assertEqual(result.result, 'FAIL')

    def test_entity_mismatch_error_contains_expected(self):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            expected_entity='Camille (French singer, born 1978)',
            detected_entity='Camille Claudel (French sculptor, 1864–1943)',
            mismatch_reason='Different entity',
        ))
        self.assertTrue(len(result.errors) >= 1)
        combined = ' '.join(result.errors)
        self.assertIn('Camille (French singer', combined)
        self.assertIn('Camille Claudel', combined)

    def test_entity_mismatch_populates_all_fields(self):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            expected_entity='Seal (British-Nigerian singer)',
            detected_entity='seal (marine animal)',
            mismatch_reason='Animal, not musician',
            entity_confidence=0.99,
        ))
        self.assertFalse(result.entity_match)
        self.assertEqual(result.expected_entity, 'Seal (British-Nigerian singer)')
        self.assertEqual(result.detected_entity, 'seal (marine animal)')
        self.assertEqual(result.mismatch_reason, 'Animal, not musician')
        self.assertAlmostEqual(result.entity_confidence, 0.99)

    def test_editorial_weak_does_not_override_entity_fail(self):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            editorial_quality='weak',
            result='FAIL',
        ))
        self.assertEqual(result.result, 'FAIL')
        # Weak editorial warning should still be present
        self.assertTrue(any('weak' in w.lower() for w in result.warnings))


class TestRegressionAmbiguousPairs(unittest.TestCase):
    """Regression suite for all known ambiguous entity pairs.

    Each test verifies that a vision response reporting entity_match=false
    for a known ambiguous pair correctly produces FAIL with populated fields.
    Add new pairs to AMBIGUOUS_PAIRS above when new editorial failures occur.
    """

    def setUp(self):
        self.provider = _make_provider()

    def _check_pair(self, expected_entity, detected_entity, mismatch_reason):
        result = self.provider._parse_response(_response_json(
            entity_match=False,
            expected_entity=expected_entity,
            detected_entity=detected_entity,
            mismatch_reason=mismatch_reason,
            result='PASS',  # model incorrectly says PASS — ensure we override
        ))
        self.assertEqual(result.result, 'FAIL',
            f"Expected FAIL for {expected_entity!r} vs {detected_entity!r}")
        self.assertFalse(result.entity_match)
        self.assertEqual(result.expected_entity, expected_entity)
        self.assertEqual(result.detected_entity, detected_entity)
        self.assertTrue(len(result.errors) >= 1,
            f"Expected at least one error for {expected_entity!r} vs {detected_entity!r}")


for _test_id, _expected, _detected, _reason in AMBIGUOUS_PAIRS:
    def _make_test(exp, det, rsn):
        def test(self):
            self._check_pair(exp, det, rsn)
        return test

    setattr(
        TestRegressionAmbiguousPairs,
        f'test_{_test_id}',
        _make_test(_expected, _detected, _reason),
    )


class TestParseEdgeCases(unittest.TestCase):
    """_parse_response handles missing/malformed entity fields gracefully."""

    def setUp(self):
        self.provider = _make_provider()

    def test_missing_entity_fields_default_to_safe_values(self):
        # Response that has no entity fields at all (old-format response)
        minimal = json.dumps({
            'person_match': True,
            'context_match': True,
            'technical_pass': True,
            'editorial_quality': 'adequate',
            'issues': [],
            'confidence': 0.9,
            'result': 'PASS',
        })
        result = self.provider._parse_response(minimal)
        # entity_match defaults True → no forced FAIL
        self.assertTrue(result.entity_match)
        self.assertEqual(result.result, 'PASS')

    def test_malformed_json_returns_uncertain(self):
        result = self.provider._parse_response('not json at all')
        self.assertEqual(result.result, 'UNCERTAIN')
        self.assertTrue(len(result.errors) >= 1)

    def test_entity_match_false_string_is_handled(self):
        # Some models return "false" as a string
        data = json.dumps({
            'person_match': True,
            'context_match': True,
            'technical_pass': True,
            'editorial_quality': 'adequate',
            'entity_match': False,
            'expected_entity': 'Eagles (band)',
            'detected_entity': 'bald eagle',
            'entity_confidence': 0.98,
            'mismatch_reason': 'Bird, not band',
            'issues': [],
            'confidence': 0.9,
            'result': 'PASS',
        })
        result = self.provider._parse_response(data)
        self.assertEqual(result.result, 'FAIL')
        self.assertFalse(result.entity_match)


if __name__ == '__main__':
    unittest.main()

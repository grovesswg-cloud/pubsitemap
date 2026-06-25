"""Unit tests for ClaudeEditorialProvider._parse_response.

Tests confirm that:
- Structured issues are parsed correctly
- FAIL-severity issues force overall_result=FAIL regardless of the model's result field
- WARN/INFO issues allow publication (no FAIL override)
- Empty issue list → PASS
- Malformed JSON → UNCERTAIN
- Missing optional fields have safe defaults
"""
import json
import unittest
from unittest.mock import MagicMock, patch


def _make_provider():
    from providers.base import EditorialStandard
    standard = EditorialStandard(
        publication_name='TestPub',
        voice_prompt='TestPub has a clear, precise editorial voice.',
    )
    with patch('anthropic.Anthropic', return_value=MagicMock()):
        from providers.impl.claude_editorial import ClaudeEditorialProvider
        return ClaudeEditorialProvider(api_key='test-key', model='test-model', editorial_standard=standard)


def _response_json(
    *,
    overall_result: str = 'PASS',
    confidence: float = 0.88,
    summary: str = 'Well-written piece.',
    issues: list | None = None,
    recommendations: list | None = None,
    notes: list | None = None,
) -> str:
    return json.dumps({
        'overall_result': overall_result,
        'confidence': confidence,
        'summary': summary,
        'issues': issues or [],
        'recommendations': recommendations or [],
        'notes': notes or [],
    })


def _issue(severity='WARN', category='pacing', description='Pacing issue.', quote=''):
    return {'severity': severity, 'category': category, 'description': description, 'quote': quote}


class TestEditorialReviewPass(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_clean_article_passes(self):
        result = self.provider._parse_response(_response_json())
        self.assertEqual(result.result, 'PASS')
        self.assertEqual(result.issues, [])

    def test_confidence_populated(self):
        result = self.provider._parse_response(_response_json(confidence=0.91))
        self.assertAlmostEqual(result.confidence, 0.91)

    def test_summary_populated(self):
        result = self.provider._parse_response(_response_json(summary='Strong lede, clear close.'))
        self.assertEqual(result.summary, 'Strong lede, clear close.')

    def test_warn_issue_does_not_block(self):
        result = self.provider._parse_response(_response_json(
            overall_result='PASS',
            issues=[_issue(severity='WARN')],
        ))
        self.assertEqual(result.result, 'PASS')
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, 'WARN')

    def test_info_issue_does_not_block(self):
        result = self.provider._parse_response(_response_json(
            overall_result='PASS',
            issues=[_issue(severity='INFO', category='clarity', description='Minor phrasing note.')],
        ))
        self.assertEqual(result.result, 'PASS')

    def test_recommendations_populated(self):
        result = self.provider._parse_response(_response_json(
            recommendations=['Tighten paragraph 3.'],
        ))
        self.assertEqual(result.recommendations, ['Tighten paragraph 3.'])

    def test_notes_populated(self):
        result = self.provider._parse_response(_response_json(
            notes=['Lede is strong.', 'Conclusion lands.'],
        ))
        self.assertEqual(result.notes, ['Lede is strong.', 'Conclusion lands.'])


class TestEditorialReviewFail(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_fail_issue_causes_fail(self):
        result = self.provider._parse_response(_response_json(
            overall_result='FAIL',
            issues=[_issue(severity='FAIL', category='structure', description='No discernible structure.')],
        ))
        self.assertEqual(result.result, 'FAIL')

    def test_fail_issue_overrides_model_pass(self):
        """If model says PASS but issues list contains FAIL, we must override to FAIL."""
        result = self.provider._parse_response(_response_json(
            overall_result='PASS',  # model incorrectly says PASS
            issues=[_issue(severity='FAIL', category='structure', description='No conclusion.')],
        ))
        self.assertEqual(result.result, 'FAIL')

    def test_fail_issue_fields_populated(self):
        result = self.provider._parse_response(_response_json(
            overall_result='FAIL',
            issues=[_issue(
                severity='FAIL',
                category='coherence',
                description='Article contradicts itself.',
                quote='On one hand... on the other hand...',
            )],
        ))
        issue = result.issues[0]
        self.assertEqual(issue.severity, 'FAIL')
        self.assertEqual(issue.category, 'coherence')
        self.assertIn('contradicts', issue.description)
        self.assertIn('On one hand', issue.quote)

    def test_mixed_severity_with_fail_blocks(self):
        """Any FAIL in the issues list forces the overall result to FAIL."""
        result = self.provider._parse_response(_response_json(
            overall_result='PASS',
            issues=[
                _issue(severity='INFO'),
                _issue(severity='WARN'),
                _issue(severity='FAIL', category='structure', description='No lede.'),
            ],
        ))
        self.assertEqual(result.result, 'FAIL')
        self.assertEqual(len(result.issues), 3)

    def test_empty_body_fail(self):
        """Provider should FAIL immediately on empty body without calling the API."""
        result = self.provider.review({'title': 'Test', 'body': '', 'type': 'bulletin'})
        self.assertEqual(result.result, 'FAIL')
        self.assertTrue(any(i.severity == 'FAIL' for i in result.issues))


class TestEditorialReviewUncertain(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_uncertain_result_parsed(self):
        result = self.provider._parse_response(_response_json(overall_result='UNCERTAIN'))
        self.assertEqual(result.result, 'UNCERTAIN')

    def test_malformed_json_returns_uncertain(self):
        result = self.provider._parse_response('not json at all')
        self.assertEqual(result.result, 'UNCERTAIN')
        self.assertTrue(len(result.summary) > 0)

    def test_invalid_result_value_becomes_uncertain(self):
        data = json.dumps({'overall_result': 'MAYBE', 'confidence': 0.5, 'issues': []})
        result = self.provider._parse_response(data)
        self.assertEqual(result.result, 'UNCERTAIN')


class TestEditorialReviewEdgeCases(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_missing_optional_fields_safe(self):
        minimal = json.dumps({'overall_result': 'PASS', 'confidence': 0.8})
        result = self.provider._parse_response(minimal)
        self.assertEqual(result.result, 'PASS')
        self.assertEqual(result.issues, [])
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.notes, [])
        self.assertEqual(result.summary, '')

    def test_invalid_severity_defaults_to_info(self):
        result = self.provider._parse_response(_response_json(
            issues=[_issue(severity='CRITICAL')],  # not a valid severity
        ))
        self.assertEqual(result.issues[0].severity, 'INFO')

    def test_non_dict_issue_skipped(self):
        data = json.dumps({
            'overall_result': 'PASS',
            'confidence': 0.8,
            'issues': ['this is a string, not a dict'],
        })
        result = self.provider._parse_response(data)
        self.assertEqual(result.issues, [])

    def test_markdown_fenced_json_parsed(self):
        fenced = '```json\n' + json.dumps({
            'overall_result': 'PASS',
            'confidence': 0.85,
            'summary': 'Good.',
            'issues': [],
            'recommendations': [],
            'notes': [],
        }) + '\n```'
        result = self.provider._parse_response(fenced)
        self.assertEqual(result.result, 'PASS')

    def test_provider_error_returns_uncertain(self):
        """API error during review() → UNCERTAIN, not an exception."""
        provider = _make_provider()
        provider._client.messages.create.side_effect = Exception("API timeout")
        result = provider.review({'title': 'Test', 'body': 'Some body text here.', 'type': 'bulletin'})
        self.assertEqual(result.result, 'UNCERTAIN')


if __name__ == '__main__':
    unittest.main()

"""Unit tests for LocalSearchReadinessProvider.evaluate.

Tests confirm that:
- A complete, well-formed article passes with no issues
- Missing title → FAIL (only objective failure that blocks)
- Long/short title → WARN (does not block)
- Missing/long/short deck → WARN (does not block)
- Title == deck → WARN (duplicate_metadata)
- H1 in body → WARN
- H3 without H2 → WARN
- No hero image → WARN (open_graph)
- Missing/generic hero alt text → WARN
- Inline images without alt → WARN
- Missing date → WARN
- No internal links → INFO (never blocks)
- WARN/INFO issues result in PASS, not FAIL
"""
import unittest

from providers.impl.local_search_readiness import LocalSearchReadinessProvider


def _make_provider():
    return LocalSearchReadinessProvider()


def _article(
    *,
    title='The Miseducation of Lauryn Hill Was Always a Warning',
    deck='Twenty-five years on, Hill\'s masterwork reveals itself not as a celebration but as a document of what the industry does to genius.',
    body='<p>Opening paragraph. See <a href="../articles/related.html">related piece</a>.</p><h2>Section One</h2><p>Body content.</p><p>More content.</p>',
    date='2026-06-25',
    image='https://example.com/lauryn.jpg',
    image_alt='Lauryn Hill performing at the 1999 Grammy Awards',
):
    return {
        'title': title,
        'deck': deck,
        'body': body,
        'date': date,
        'image': image,
        'imageAlt': image_alt,
    }


class TestSearchReadinessPass(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_clean_article_passes(self):
        result = self.provider.evaluate(_article())
        self.assertEqual(result.result, 'PASS')
        self.assertEqual(result.issues, [])

    def test_summary_present_on_pass(self):
        result = self.provider.evaluate(_article())
        self.assertTrue(len(result.summary) > 0)

    def test_warn_only_does_not_block(self):
        result = self.provider.evaluate(_article(deck=''))
        self.assertEqual(result.result, 'PASS')
        self.assertTrue(any(i.severity == 'WARN' for i in result.issues))

    def test_info_only_does_not_block(self):
        result = self.provider.evaluate(_article(body='<p>No links here.</p>'))
        self.assertEqual(result.result, 'PASS')

    def test_h2_without_h3_passes(self):
        body = '<p>Intro.</p><h2>Section</h2><p>Content.</p>'
        result = self.provider.evaluate(_article(body=body))
        headings_issues = [i for i in result.issues if i.category == 'headings']
        self.assertEqual(headings_issues, [])


class TestSearchReadinessFail(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_missing_title_fails(self):
        result = self.provider.evaluate(_article(title=''))
        self.assertEqual(result.result, 'FAIL')

    def test_missing_title_issue_category(self):
        result = self.provider.evaluate(_article(title=''))
        self.assertTrue(any(i.category == 'title' and i.severity == 'FAIL' for i in result.issues))

    def test_fail_result_has_blocking_summary(self):
        result = self.provider.evaluate(_article(title=''))
        self.assertIn('blocked', result.summary.lower())


class TestSearchReadinessTitleWarnings(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_long_title_warns(self):
        result = self.provider.evaluate(_article(title='A' * 71))
        categories = [i.category for i in result.issues]
        self.assertIn('title', categories)
        title_issues = [i for i in result.issues if i.category == 'title']
        self.assertTrue(any(i.severity == 'WARN' for i in title_issues))

    def test_short_title_warns(self):
        result = self.provider.evaluate(_article(title='Short'))
        title_issues = [i for i in result.issues if i.category == 'title']
        self.assertTrue(any(i.severity == 'WARN' for i in title_issues))

    def test_exact_70_chars_no_warn(self):
        result = self.provider.evaluate(_article(title='A' * 70))
        long_warns = [
            i for i in result.issues
            if i.category == 'title' and 'truncated' in i.description
        ]
        self.assertEqual(long_warns, [])

    def test_exact_10_chars_no_short_warn(self):
        result = self.provider.evaluate(_article(title='A' * 10))
        short_warns = [
            i for i in result.issues
            if i.category == 'title' and 'short' in i.description.lower()
        ]
        self.assertEqual(short_warns, [])


class TestSearchReadinessDeckWarnings(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_missing_deck_warns(self):
        result = self.provider.evaluate(_article(deck=''))
        cats = [i.category for i in result.issues]
        self.assertIn('meta_description', cats)

    def test_long_deck_warns(self):
        result = self.provider.evaluate(_article(deck='A' * 161))
        deck_issues = [i for i in result.issues if i.category == 'meta_description']
        self.assertTrue(any('truncated' in i.description for i in deck_issues))

    def test_short_deck_warns(self):
        result = self.provider.evaluate(_article(deck='Too short.'))
        deck_issues = [i for i in result.issues if i.category == 'meta_description']
        self.assertTrue(any(i.severity == 'WARN' for i in deck_issues))

    def test_title_equals_deck_warns(self):
        shared = 'Lauryn Hill Review'
        result = self.provider.evaluate(_article(title=shared, deck=shared))
        cats = [i.category for i in result.issues]
        self.assertIn('duplicate_metadata', cats)


class TestSearchReadinessHeadings(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_h1_in_body_warns(self):
        body = '<p>Intro.</p><h1>Subheading</h1><p>Content.</p>'
        result = self.provider.evaluate(_article(body=body))
        heading_issues = [i for i in result.issues if i.category == 'headings']
        self.assertTrue(any(i.severity == 'WARN' for i in heading_issues))

    def test_h3_without_h2_warns(self):
        body = '<p>Intro.</p><h3>Sub-sub</h3><p>Content.</p>'
        result = self.provider.evaluate(_article(body=body))
        heading_issues = [i for i in result.issues if i.category == 'headings']
        self.assertTrue(any('H3' in i.description for i in heading_issues))

    def test_h3_with_h2_no_warn(self):
        body = '<p>Intro.</p><h2>Section</h2><h3>Sub</h3><p>Content.</p>'
        result = self.provider.evaluate(_article(body=body))
        skip_warns = [
            i for i in result.issues
            if i.category == 'headings' and 'skipped' in i.description.lower()
        ]
        self.assertEqual(skip_warns, [])


class TestSearchReadinessImages(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_no_hero_image_warns_open_graph(self):
        result = self.provider.evaluate(_article(image='', image_alt=''))
        og_issues = [i for i in result.issues if i.category == 'open_graph']
        self.assertTrue(any(i.severity == 'WARN' for i in og_issues))

    def test_missing_hero_alt_warns(self):
        result = self.provider.evaluate(_article(image_alt=''))
        alt_issues = [i for i in result.issues if i.category == 'image_metadata']
        self.assertTrue(any('missing' in i.description.lower() for i in alt_issues))

    def test_generic_hero_alt_warns(self):
        for generic in ('image', 'photo', 'picture', 'img', 'figure'):
            with self.subTest(alt=generic):
                result = self.provider.evaluate(_article(image_alt=generic))
                alt_issues = [i for i in result.issues if i.category == 'image_metadata']
                self.assertTrue(any('generic' in i.description.lower() for i in alt_issues))

    def test_descriptive_alt_passes(self):
        result = self.provider.evaluate(_article(image_alt='Lauryn Hill at the 1999 Grammy Awards'))
        alt_issues = [i for i in result.issues if i.category == 'image_metadata']
        self.assertEqual(alt_issues, [])

    def test_inline_image_missing_alt_warns(self):
        body = '<p>Text.</p><img src="x.jpg"><p>More.</p>'
        result = self.provider.evaluate(_article(body=body))
        alt_issues = [i for i in result.issues if i.category == 'image_metadata']
        inline_warns = [i for i in alt_issues if 'inline' in i.description.lower()]
        self.assertTrue(len(inline_warns) > 0)

    def test_inline_image_empty_alt_warns(self):
        body = '<p>Text.</p><img src="x.jpg" alt=""><p>More.</p>'
        result = self.provider.evaluate(_article(body=body))
        alt_issues = [i for i in result.issues if i.category == 'image_metadata']
        inline_warns = [i for i in alt_issues if 'inline' in i.description.lower()]
        self.assertTrue(len(inline_warns) > 0)


class TestSearchReadinessStructuredData(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_missing_date_warns(self):
        result = self.provider.evaluate(_article(date=''))
        sd_issues = [i for i in result.issues if i.category == 'structured_data']
        self.assertTrue(any(i.severity == 'WARN' for i in sd_issues))

    def test_date_present_no_structured_data_warn(self):
        result = self.provider.evaluate(_article(date='2026-06-25'))
        sd_issues = [i for i in result.issues if i.category == 'structured_data']
        self.assertEqual(sd_issues, [])


class TestSearchReadinessInternalLinks(unittest.TestCase):

    def setUp(self):
        self.provider = _make_provider()

    def test_no_internal_links_is_info(self):
        body = '<p>No links at all.</p>'
        result = self.provider.evaluate(_article(body=body))
        link_issues = [i for i in result.issues if i.category == 'internal_links']
        self.assertTrue(any(i.severity == 'INFO' for i in link_issues))

    def test_no_internal_links_does_not_block(self):
        body = '<p>No links at all.</p>'
        result = self.provider.evaluate(_article(body=body))
        self.assertEqual(result.result, 'PASS')

    def test_relative_link_clears_check(self):
        body = '<p>See <a href="../articles/foo.html">this article</a>.</p>'
        result = self.provider.evaluate(_article(body=body))
        link_issues = [i for i in result.issues if i.category == 'internal_links']
        self.assertEqual(link_issues, [])

    def test_root_relative_link_clears_check(self):
        body = '<p>See <a href="/articles/foo.html">this</a>.</p>'
        result = self.provider.evaluate(_article(body=body))
        link_issues = [i for i in result.issues if i.category == 'internal_links']
        self.assertEqual(link_issues, [])


if __name__ == '__main__':
    unittest.main()

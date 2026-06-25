"""Regression tests for multi-image vision verification in the publication pipeline.

These tests guard against the failure class where inline images bypass vision
verification because only images[0] (hero) was checked.

Production failure that triggered this suite (2026-06-25):
  Feature article about Linea Personal published with two incorrect inline
  images (Manny Carlton, Alejandra Ávalos). Hero was vision-checked; inlines
  were not. Additionally, QUALITY_IMAGE_VALIDATION was never enabled in the
  production workflow files — the gate was built but never activated.

Test coverage:
  - Empty image list → returns []
  - Gate disabled → all images pass through unchanged
  - Single hero pass → returns [hero]
  - Single hero fail → returns [] (blocks article)
  - Hero fail → inlines never checked (efficient abort)
  - Hero pass, all inlines pass → returns all images
  - Hero pass, one inline fails → drops that inline, keeps others
  - Hero pass, all inlines fail → returns [hero] only
  - Three-image feature (Linea Personal regression): all checked
  - Three-image feature: second inline fail caught and dropped
  - Three-image feature: third inline fail caught and dropped
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

# Stub heavy external packages and scheduler sibling modules so the test runner
# doesn't need the full production dependency set installed.
for _mod in ('feedparser', 'anthropic', 'requests', 'schedule',
             'google', 'google.generativeai'):
    sys.modules.setdefault(_mod, MagicMock())
for _mod in ('news_fetcher', 'article_writer', 'feature_writer', 'review_writer',
             'album_finder', 'image_sourcer', 'publisher'):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules.setdefault('validators', MagicMock())
sys.modules.setdefault('validators.metadata', MagicMock())


def _make_image(idx: int) -> dict:
    return {
        'url': f'https://example.com/img{idx}.jpg',
        'provider': 'wikimedia',
        'evidenceTier': 'AUTHORITATIVE',
        'credit': f'Photo {idx}',
    }


def _make_images(n: int) -> list:
    return [_make_image(i) for i in range(n)]


def _make_article() -> dict:
    return {
        'title': 'Linea Personal and the Architecture of Argentine New Wave',
        'tags': ['linea-personal', 'new-wave', 'argentina'],
        'body': '<p>Body text.</p>',
    }


class TestRunVisionVerificationGateDisabled(unittest.TestCase):

    def test_empty_list_returns_empty(self):
        import scheduler
        result = scheduler._run_vision_verification([], _make_article())
        self.assertEqual(result, [])

    def test_gate_disabled_single_image_passes_through(self):
        import scheduler
        with patch.object(scheduler, 'QUALITY_IMAGE_VALIDATION', False):
            images = _make_images(1)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, images)

    def test_gate_disabled_three_images_all_pass_through(self):
        import scheduler
        with patch.object(scheduler, 'QUALITY_IMAGE_VALIDATION', False):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, images)


class TestRunVisionVerificationHero(unittest.TestCase):

    def test_hero_pass_single_image_returns_list_with_hero(self):
        import scheduler
        with patch.object(scheduler, '_check_one_image', return_value=True):
            images = _make_images(1)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, images)

    def test_hero_fail_returns_empty_list(self):
        import scheduler
        with patch.object(scheduler, '_check_one_image', return_value=False):
            images = _make_images(1)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, [])

    def test_hero_fail_with_inlines_returns_empty_list(self):
        import scheduler
        with patch.object(scheduler, '_check_one_image', return_value=False):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, [])

    def test_hero_fail_inlines_never_checked(self):
        # When hero fails, pipeline must not check inlines — they'd be dropped anyway
        import scheduler
        call_count = [0]

        def counting_check(image, article_data, role, image_index=0):
            call_count[0] += 1
            return False

        with patch.object(scheduler, '_check_one_image', side_effect=counting_check):
            images = _make_images(3)
            scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(call_count[0], 1)


class TestRunVisionVerificationInlineImages(unittest.TestCase):

    def test_hero_pass_all_inlines_pass_returns_all(self):
        import scheduler
        with patch.object(scheduler, '_check_one_image', return_value=True):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 3)
            self.assertEqual(result, images)

    def test_hero_pass_all_inlines_fail_returns_hero_only(self):
        import scheduler

        def hero_only(image, article_data, role, image_index=0):
            return image_index == 0

        with patch.object(scheduler, '_check_one_image', side_effect=hero_only):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], images[0])

    def test_second_inline_fail_drops_only_that_image(self):
        import scheduler

        def fail_idx_1(image, article_data, role, image_index=0):
            return image_index != 1

        with patch.object(scheduler, '_check_one_image', side_effect=fail_idx_1):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 2)
            self.assertIn(images[0], result)
            self.assertNotIn(images[1], result)
            self.assertIn(images[2], result)

    def test_third_inline_fail_drops_only_that_image(self):
        import scheduler

        def fail_idx_2(image, article_data, role, image_index=0):
            return image_index != 2

        with patch.object(scheduler, '_check_one_image', side_effect=fail_idx_2):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 2)
            self.assertIn(images[0], result)
            self.assertIn(images[1], result)
            self.assertNotIn(images[2], result)

    def test_order_preserved_after_inline_drop(self):
        import scheduler

        def fail_middle(image, article_data, role, image_index=0):
            return image_index != 2

        with patch.object(scheduler, '_check_one_image', side_effect=fail_middle):
            images = _make_images(5)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(result, [images[0], images[1], images[3], images[4]])


class TestRunVisionVerificationLineaPersonalRegression(unittest.TestCase):
    """
    Regression suite for the 2026-06-25 Linea Personal production failure.
    Feature articles source three images (one per imageQueries entry). Before
    this fix, only images[0] was vision-checked. Both inline images were
    published without any identity verification.
    """

    def test_three_image_feature_all_images_checked(self):
        import scheduler
        checked_indices = []

        def record_checks(image, article_data, role, image_index=0):
            checked_indices.append(image_index)
            return True

        with patch.object(scheduler, '_check_one_image', side_effect=record_checks):
            images = _make_images(3)
            scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(sorted(checked_indices), [0, 1, 2])

    def test_three_image_feature_wrong_second_image_caught(self):
        # Regression: Manny Carlton image at idx=1 should be caught and dropped
        import scheduler

        def manny_carlton_at_1(image, article_data, role, image_index=0):
            return image_index != 1  # idx=1 is the wrong person

        with patch.object(scheduler, '_check_one_image', side_effect=manny_carlton_at_1):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 2)
            self.assertNotIn(images[1], result)

    def test_three_image_feature_wrong_third_image_caught(self):
        # Regression: Alejandra Ávalos image at idx=2 should be caught and dropped
        import scheduler

        def avalos_at_2(image, article_data, role, image_index=0):
            return image_index != 2  # idx=2 is the wrong person

        with patch.object(scheduler, '_check_one_image', side_effect=avalos_at_2):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 2)
            self.assertNotIn(images[2], result)

    def test_three_image_feature_both_inlines_wrong_publishes_hero_only(self):
        # Both inlines wrong — article should publish with hero only, not be blocked
        import scheduler

        def hero_correct_inlines_wrong(image, article_data, role, image_index=0):
            return image_index == 0

        with patch.object(scheduler, '_check_one_image', side_effect=hero_correct_inlines_wrong):
            images = _make_images(3)
            result = scheduler._run_vision_verification(images, _make_article())
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], images[0])
            # Article is NOT blocked — hero was correct
            self.assertNotEqual(result, [])


if __name__ == '__main__':
    unittest.main()

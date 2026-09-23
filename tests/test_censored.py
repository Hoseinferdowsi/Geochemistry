# -*- coding: utf-8 -*-
"""تست‌های واحد پردازش داده‌های سانسورشده (< و >)."""
import unittest

import numpy as np

from processing_services import CENSORED_VALUE_PATTERN, _fix_censored_value


class TestFixCensoredValue(unittest.TestCase):
    def test_left_censored(self):
        # <0.5 با ضریب 0.75 → 0.375
        self.assertAlmostEqual(_fix_censored_value('<0.5', 0.75, 1.25), 0.375)

    def test_right_censored(self):
        # >10 با ضریب 1.25 → 12.5
        self.assertAlmostEqual(_fix_censored_value('>10', 0.75, 1.25), 12.5)

    def test_space_after_sign(self):
        self.assertAlmostEqual(_fix_censored_value('> 2.5', 0.75, 1.25), 3.125)

    def test_custom_coefficients(self):
        self.assertAlmostEqual(_fix_censored_value('<4', 0.5, 2.0), 2.0)
        self.assertAlmostEqual(_fix_censored_value('>4', 0.5, 2.0), 8.0)

    def test_scientific_notation(self):
        self.assertAlmostEqual(_fix_censored_value('>1.2e2', 0.75, 1.25), 150.0)

    def test_plain_number_string_unchanged(self):
        self.assertEqual(_fix_censored_value('5', 0.75, 1.25), '5')

    def test_numeric_input_unchanged(self):
        self.assertEqual(_fix_censored_value(7.5, 0.75, 1.25), 7.5)

    def test_nan_unchanged(self):
        self.assertTrue(np.isnan(_fix_censored_value(np.nan, 0.75, 1.25)))

    def test_empty_string_unchanged(self):
        self.assertEqual(_fix_censored_value('', 0.75, 1.25), '')
        self.assertEqual(_fix_censored_value('   ', 0.75, 1.25), '   ')

    def test_invalid_text_unchanged(self):
        self.assertEqual(_fix_censored_value('<abc', 0.75, 1.25), '<abc')
        self.assertEqual(_fix_censored_value('n/a', 0.75, 1.25), 'n/a')


class TestCensoredPattern(unittest.TestCase):
    def test_matches_valid_censored(self):
        for text in ('<0.5', '>10', '< 3', '>2.5e3', '<0'):
            self.assertIsNotNone(CENSORED_VALUE_PATTERN.match(text), text)

    def test_rejects_plain_or_invalid(self):
        for text in ('5', 'abc', '<>', '=5', 'a<5', '<<5'):
            self.assertIsNone(CENSORED_VALUE_PATTERN.match(text), text)


if __name__ == '__main__':
    unittest.main()

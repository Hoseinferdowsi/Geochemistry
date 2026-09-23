# -*- coding: utf-8 -*-
"""تست‌های واحد تشخیص مقادیر خارج از رده (IQR، Z-Score، Dörfel)."""
import unittest

import numpy as np
import pandas as pd

from outliers import (
    detect_outliers_dorfel,
    detect_outliers_iqr,
    detect_outliers_zscore,
    get_g_coefficient,
)


class TestIQR(unittest.TestCase):
    def test_flags_extreme_value(self):
        data = pd.Series([10.0, 11, 12, 13, 14, 15, 100.0])
        outliers, repl = detect_outliers_iqr(data)
        self.assertTrue(bool(outliers.iloc[-1]))
        self.assertFalse(bool(outliers.iloc[0]))
        # مقدار جایگزین باید کمتر از مقدار اصلی پرت باشد
        self.assertLess(repl[outliers].iloc[0], 100.0)

    def test_no_outliers_in_tight_data(self):
        data = pd.Series([5.0, 5.1, 4.9, 5.0, 5.2, 4.8, 5.05, 4.95])
        outliers, _ = detect_outliers_iqr(data)
        self.assertEqual(int(outliers.sum()), 0)

    def test_low_outlier_also_flagged(self):
        data = pd.Series([1.0, 10.0, 11, 12, 13, 14, 15])
        outliers, _ = detect_outliers_iqr(data)
        self.assertTrue(bool(outliers.iloc[0]))


class TestZScore(unittest.TestCase):
    def test_flags_beyond_threshold(self):
        rng = np.random.default_rng(0)
        data = pd.Series(rng.normal(0, 1, 200))
        data.iloc[7] = 10.0  # پرت آشکار
        outliers, repl = detect_outliers_zscore(data, threshold=3)
        outliers = np.asarray(outliers)  # خروجی آرایه numpy است
        self.assertTrue(bool(outliers[7]))
        self.assertEqual(int(outliers.sum()), 1)
        # جایگزین باید روی مرز آستانه باشد
        mean, std = data.mean(), data.std()
        self.assertAlmostEqual(repl.iloc[7], mean + 3 * std)

    def test_clean_data_no_outliers(self):
        data = pd.Series([0.0, 0.5, -0.5, 1.0, -1.0, 0.2, -0.2])
        outliers, _ = detect_outliers_zscore(data, threshold=3)
        self.assertEqual(int(np.asarray(outliers).sum()), 0)


class TestDorfel(unittest.TestCase):
    def test_extreme_value_replaced(self):
        data = pd.Series([10.0, 11, 12, 13, 14, 15, 16, 17, 18, 100.0])
        result = detect_outliers_dorfel(data)
        self.assertEqual(len(result), len(data))
        self.assertTrue(np.isfinite(result).all())
        self.assertLess(result.iloc[-1], 100.0)  # جایگزین شده
        # مقادیر عادی دست‌نخورده می‌مانند
        self.assertEqual(result.iloc[0], 10.0)

    def test_returns_series(self):
        data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = detect_outliers_dorfel(data)
        self.assertIsInstance(result, pd.Series)
        self.assertTrue(np.isfinite(result).all())


class TestGCoefficient(unittest.TestCase):
    def test_positive_float_for_common_sizes(self):
        for n in (4, 5, 7, 10, 30, 50, 100, 999, 1000):
            g = get_g_coefficient(n)
            # مقادیر جدول ممکن است int باشند — عددی و مثبت
            self.assertIsInstance(g, (int, float))
            self.assertGreater(float(g), 0)

    def test_clamps_out_of_range(self):
        self.assertEqual(get_g_coefficient(2), get_g_coefficient(4))
        self.assertEqual(get_g_coefficient(5000), get_g_coefficient(1000))

    def test_interpolation_between_table_points(self):
        g_lower = get_g_coefficient(10)
        g_upper = get_g_coefficient(20)
        g_mid = get_g_coefficient(15)
        self.assertGreaterEqual(min(g_lower, g_upper) - 1e-9, 0)
        # مقدار درونیابی شده باید بین دو سر جدول باشد
        self.assertLessEqual(min(g_lower, g_upper) - 1e-9, g_mid)
        self.assertLessEqual(g_mid, max(g_lower, g_upper) + 1e-9)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""تست‌های واحد تبدیل‌های نرمال‌سازی، درون‌یابی IDW و ابزارهای چندمتغیره."""
import unittest

import numpy as np
import scipy.stats as stats

from processing_services import (
    TRANSFORM_METHODS,
    _anomaly_class_label,
    _idw_interpolation,
    _log_transform,
    _promax_rotation,
    _shapiro_wilk_test,
    _skewness,
    _sqrt_transform,
    _varimax_rotation,
)


def _unwrap(out):
    """برخی تبدیل‌ها (Box-Cox، Yeo-Johnson) کورتیو (نتیجه، lambda) برمی‌گردانند."""
    return out[0] if isinstance(out, tuple) else out


class TestTransformRegistry(unittest.TestCase):
    def test_all_six_methods_registered(self):
        expected = {'Box-Cox', 'Yeo-Johnson', 'Quantile', 'Rank-Based', 'Log', 'Sqrt'}
        self.assertEqual(set(TRANSFORM_METHODS.keys()), expected)

    def test_length_and_nan_positions_preserved(self):
        data = np.array([2.0, 5.0, np.nan, 11.0, 4.0, 8.0, 20.0, 3.5, 9.0, 6.0])
        nan_mask = np.isnan(data)
        for name, fn in TRANSFORM_METHODS.items():
            out = _unwrap(fn(data))
            self.assertEqual(len(out), len(data), name)
            self.assertTrue(np.isnan(out[nan_mask]).all(), name)
            self.assertTrue(np.isfinite(out[~nan_mask]).all(), name)

    def test_too_few_points_returns_input(self):
        data = np.array([1.0, np.nan, 3.0])  # فقط ۲ مقدار معتبر
        for name, fn in TRANSFORM_METHODS.items():
            out = _unwrap(fn(data))
            np.testing.assert_array_equal(out, data, err_msg=name)


class TestLogTransform(unittest.TestCase):
    def test_exact_values(self):
        data = np.array([1.0, np.e, np.e ** 2])
        np.testing.assert_allclose(_log_transform(data), [0.0, 1.0, 2.0], atol=1e-10)

    def test_handles_non_positive(self):
        data = np.array([-50.0, -10.0, 0.0, 5.0])
        out = _log_transform(data)
        self.assertTrue(np.isfinite(out).all())


class TestSqrtTransform(unittest.TestCase):
    def test_exact_values(self):
        data = np.array([4.0, 9.0, 16.0])
        np.testing.assert_allclose(_sqrt_transform(data), [2.0, 3.0, 4.0], atol=1e-10)

    def test_handles_negative(self):
        data = np.array([-9.0, -4.0, 1.0, 4.0])
        out = _sqrt_transform(data)
        self.assertTrue(np.isfinite(out).all())


class TestNormalityImprovement(unittest.TestCase):
    def test_rank_based_produces_normal_scores(self):
        rng = np.random.default_rng(42)
        skewed = rng.lognormal(mean=2.0, sigma=1.0, size=300)
        out = _unwrap(TRANSFORM_METHODS['Rank-Based'](skewed))
        p, _ = _shapiro_wilk_test(out)
        self.assertGreater(p, 0.01)

    def test_boxcox_reduces_skewness(self):
        rng = np.random.default_rng(7)
        skewed = rng.lognormal(mean=1.5, sigma=1.2, size=400)
        out = _unwrap(TRANSFORM_METHODS['Box-Cox'](skewed))
        before = abs(_skewness(skewed))
        after = abs(_skewness(out))
        self.assertLess(after, before)

    def test_yeojohnson_handles_negatives(self):
        rng = np.random.default_rng(11)
        data = rng.normal(loc=-5.0, scale=8.0, size=200)
        out = _unwrap(TRANSFORM_METHODS['Yeo-Johnson'](data))
        self.assertTrue(np.isfinite(out).all())


class TestIDW(unittest.TestCase):
    def test_constant_field_reproduced(self):
        rng = np.random.default_rng(3)
        x = rng.uniform(0, 100, 50)
        y = rng.uniform(0, 100, 50)
        v = np.full(50, 7.0)
        xi, yi, zi = _idw_interpolation(x, y, v)
        self.assertIsNotNone(zi)
        np.testing.assert_allclose(zi, 7.0, atol=1e-8)

    def test_nan_values_skipped(self):
        rng = np.random.default_rng(5)
        x = rng.uniform(0, 10, 30)
        y = rng.uniform(0, 10, 30)
        v = rng.normal(0, 1, 30)
        v[::3] = np.nan
        xi, yi, zi = _idw_interpolation(x, y, v)
        self.assertIsNotNone(zi)
        self.assertTrue(np.isfinite(zi).all())

    def test_too_few_points_returns_none(self):
        xi, yi, zi = _idw_interpolation(
            np.array([1.0, 2.0]), np.array([3.0, 4.0]), np.array([5.0, 6.0])
        )
        self.assertIsNone(zi)

    def test_k_parameter_respected(self):
        rng = np.random.default_rng(9)
        x = rng.uniform(0, 10, 40)
        y = rng.uniform(0, 10, 40)
        v = rng.normal(0, 1, 40)
        _, _, zi_small = _idw_interpolation(x, y, v, k=4)
        _, _, zi_big = _idw_interpolation(x, y, v, k=40)
        self.assertTrue(np.isfinite(zi_small).all())
        self.assertTrue(np.isfinite(zi_big).all())


class TestRotations(unittest.TestCase):
    def test_varimax_preserves_total_variance(self):
        rng = np.random.default_rng(1)
        L = rng.normal(0, 0.5, size=(10, 3))
        out, rot = _varimax_rotation(L)
        self.assertEqual(out.shape, L.shape)
        self.assertAlmostEqual(np.sum(out ** 2), np.sum(L ** 2), places=6)

    def test_varimax_identity_for_single_factor(self):
        L = np.array([[0.5], [0.9], [0.2]])
        out, _ = _varimax_rotation(L)
        np.testing.assert_allclose(out, L)

    def test_promax_output_finite_and_shaped(self):
        rng = np.random.default_rng(2)
        L = rng.normal(0, 0.5, size=(8, 2))
        out, rot, phi = _promax_rotation(L)
        self.assertEqual(out.shape, L.shape)
        self.assertEqual(phi.shape, (2, 2))
        self.assertTrue(np.isfinite(out).all())
        self.assertTrue(np.isfinite(phi).all())
        # قطر ماتریس همبستگی فاکتورها باید ۱ باشد
        np.testing.assert_allclose(np.diag(phi), [1.0, 1.0], atol=1e-6)


class TestAnomalyLabels(unittest.TestCase):
    def test_two_anomaly_classes(self):
        self.assertEqual([_anomaly_class_label(k, 2) for k in (1, 2)], ['خفیف', 'شدید'])

    def test_single_class(self):
        self.assertEqual(_anomaly_class_label(1, 1), 'آنومالی')

    def test_middle_classes_marked_medium(self):
        labels = [_anomaly_class_label(k, 4) for k in (1, 2, 3, 4)]
        self.assertEqual(labels[0], 'خفیف')
        self.assertEqual(labels[-1], 'شدید')
        self.assertTrue(all('متوسط' in l for l in labels[1:-1]))


if __name__ == '__main__':
    unittest.main()

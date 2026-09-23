# -*- coding: utf-8 -*-
"""تست‌های درون‌یابی کریجینگ (pykrige)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from processing_services import _kriging_interpolation


def _synth(n=120, seed=42):
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 1000, n)
    y = rng.uniform(0, 1000, n)
    values = 10 * np.sin(x / 150) * np.cos(y / 200) + rng.normal(0, 0.3, n)
    return x, y, values


class TestKrigingInterpolation(unittest.TestCase):
    def test_basic_output_shape(self):
        x, y, v = _synth()
        xi, yi, zi = _kriging_interpolation(x, y, v)
        self.assertIsNotNone(xi)
        self.assertEqual(zi.shape, xi.shape)
        self.assertEqual(zi.shape, yi.shape)

    def test_range_close_to_data(self):
        x, y, v = _synth()
        _, _, zi = _kriging_interpolation(x, y, v)
        self.assertAlmostEqual(float(np.nanmin(zi)), float(v.min()), delta=1.0)
        self.assertAlmostEqual(float(np.nanmax(zi)), float(v.max()), delta=1.0)

    def test_all_variograms(self):
        x, y, v = _synth()
        for vm in ('spherical', 'exponential', 'gaussian', 'linear'):
            xi, yi, zi = _kriging_interpolation(x, y, v, variogram_model=vm)
            self.assertIsNotNone(zi, vm)
            self.assertEqual(zi.shape, (60, 60), vm)

    def test_universal_method(self):
        x, y, v = _synth()
        xi, yi, zi = _kriging_interpolation(x, y, v, method='universal')
        self.assertIsNotNone(zi)

    def test_geo_coords_normalized(self):
        x, y, v = _synth()
        # مختصات جغرافیایی با مقیاس ناهمگون X/Y
        xg = x / 1000 + 48
        yg = y / 1000 + 30
        xi, yi, zi = _kriging_interpolation(xg, yg, v)
        self.assertIsNotNone(zi)
        self.assertFalse(np.all(np.isnan(zi)))

    def test_too_few_points(self):
        x, y, v = _synth()
        result = _kriging_interpolation(x[:3], y[:3], v[:3])
        self.assertEqual(result, (None, None, None))

    def test_nan_points_ignored(self):
        x, y, v = _synth()
        v_with_nan = v.copy()
        v_with_nan[:10] = np.nan
        xi, yi, zi = _kriging_interpolation(x, y, v_with_nan)
        self.assertIsNotNone(zi)

    def test_missing_pykrige_raises_runtime_error(self):
        import unittest.mock as mock
        x, y, v = _synth()
        with mock.patch.dict('sys.modules', {'pykrige.ok': None, 'pykrige.uk': None}):
            with self.assertRaises(RuntimeError):
                _kriging_interpolation(x, y, v)


if __name__ == '__main__':
    unittest.main()

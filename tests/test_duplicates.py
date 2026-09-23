# -*- coding: utf-8 -*-
"""تست‌های تحلیل داده‌های تکراری (Duplicate QC)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np
import pandas as pd

from processing_services import (
    _fix_censored_value_numeric,
    _duplicate_pairs_values,
    _dup_categorize,
    process_duplicate_qc,
)


class TestCensoredNumeric(unittest.TestCase):
    def test_censored_left(self):
        self.assertAlmostEqual(_fix_censored_value_numeric('<2.0', 0.75, 1.25), 1.5)

    def test_censored_right(self):
        self.assertAlmostEqual(_fix_censored_value_numeric('>10', 0.75, 1.25), 12.5)

    def test_plain_number(self):
        self.assertAlmostEqual(_fix_censored_value_numeric(5.5, 0.75, 1.25), 5.5)

    def test_text_to_nan(self):
        self.assertTrue(np.isnan(_fix_censored_value_numeric('ND', 0.75, 1.25)))

    def test_none_to_nan(self):
        self.assertTrue(np.isnan(_fix_censored_value_numeric(None, 0.75, 1.25)))


class TestCategorize(unittest.TestCase):
    def test_good(self):
        self.assertEqual(_dup_categorize(5, 5), 'خوب')

    def test_acceptable(self):
        self.assertEqual(_dup_categorize(15, 15), 'قابل قبول')

    def test_poor(self):
        self.assertEqual(_dup_categorize(25, 10), 'ضعیف')
        self.assertEqual(_dup_categorize(5, 30), 'ضعیف')


class TestDuplicatePairsValues(unittest.TestCase):
    def _make(self):
        duplicate_samples = pd.DataFrame({
            'Sample_ID': ['S1', 'S2'],
            'Duplicated_Sample_ID': ['D1', 'D2'],
        })
        duplicate_data = pd.DataFrame({
            'Sample_ID': ['S1', 'S2', 'D1', 'D2'],
            'Au': ['1.0', '2.0', '<1.0', '>4.0'],
            'Cu': [10.0, 20.0, 10.5, 21.0],
        })
        return duplicate_samples, duplicate_data

    def test_pair_extraction_with_censored(self):
        ds, dd = self._make()
        pairs = _duplicate_pairs_values(ds, dd, 'Au', 0.75, 1.25)
        self.assertEqual(len(pairs), 2)
        self.assertAlmostEqual(pairs[0][0], 1.0)
        self.assertAlmostEqual(pairs[0][1], 0.75)  # <1.0 × 0.75
        self.assertAlmostEqual(pairs[1][1], 5.0)   # >4.0 × 1.25

    def test_missing_sample_skipped(self):
        ds, dd = self._make()
        dd = dd[~dd['Sample_ID'].isin(['D1'])]
        pairs = _duplicate_pairs_values(ds, dd, 'Au', 0.75, 1.25)
        self.assertEqual(len(pairs), 1)

    def test_duplicate_ids_first_match(self):
        ds, dd = self._make()
        # نام تکراری: اولین ردیف استفاده می‌شود
        extra = pd.DataFrame({'Sample_ID': ['S1'], 'Au': ['9.9'], 'Cu': [99.0]})
        dd2 = pd.concat([extra, dd], ignore_index=True)
        pairs = _duplicate_pairs_values(ds, dd2, 'Au', 0.75, 1.25)
        self.assertAlmostEqual(pairs[0][0], 9.9)


class TestProcessDuplicateQcIntegration(unittest.TestCase):
    def test_end_to_end_id_based(self):
        import tempfile
        from processing_services import (
            save_session_state, load_session_state, get_session_dir,
        )
        rng = np.random.default_rng(11)
        sid = 'ut_dup_test'
        sess_dir = get_session_dir(sid)
        os.makedirs(sess_dir, exist_ok=True)
        try:
            data_main = pd.DataFrame({
                'Sample_ID': [f'S{i+1}' for i in range(10)],
                **{el: rng.normal(50, 5, 10).round(2) for el in ['Au', 'Cu']},
            })
            dup_rows = data_main.iloc[:6].copy()
            dup_rows['Sample_ID'] = [f'D{i+1}' for i in range(6)]
            dup_rows['Au'] = (dup_rows['Au'] * rng.uniform(0.9, 1.1, 6)).round(2)
            dup_data = pd.concat([data_main, dup_rows], ignore_index=True)
            dup_samples = pd.DataFrame({
                'Sample_ID': data_main['Sample_ID'].iloc[:6],
                'Duplicated_Sample_ID': [f'D{i+1}' for i in range(6)],
            })
            xlsx = os.path.join(sess_dir, 'original.xlsx')
            with pd.ExcelWriter(xlsx, engine='openpyxl') as w:
                data_main.to_excel(w, sheet_name='Data', index=False)
                dup_samples.to_excel(w, sheet_name='Duplicate Samples', index=False)
                dup_data.to_excel(w, sheet_name='Duplicate_Data', index=False)
            state = {'uploaded_file': 'original.xlsx', 'user_x_col': None, 'user_y_col': None, 'steps': {}}
            save_session_state(sid, state)

            result = process_duplicate_qc(sid, source='original')
            self.assertTrue(result['success'])
            self.assertEqual(len(result['stats']), 2)
            self.assertEqual(result['pair_source'], 'id-based')
            for s in result['stats']:
                self.assertIn('Mean_RPD', s)
                self.assertIn(s['Quality_Category'], ('خوب', 'قابل قبول', 'ضعیف'))
        finally:
            shutil.rmtree(sess_dir, ignore_errors=True)

    def test_min_pairs_guard(self):
        # کمتر از ۴ زوج → خطا
        import tempfile
        from processing_services import save_session_state, get_session_dir
        sid = 'ut_dup_min'
        sess_dir = get_session_dir(sid)
        os.makedirs(sess_dir, exist_ok=True)
        try:
            data_main = pd.DataFrame({
                'Sample_ID': ['S1', 'S2'],
                'Au': [1.0, 2.0],
            })
            dup_data = pd.DataFrame({'Sample_ID': ['S1', 'S2', 'D1', 'D2'], 'Au': [1.0, 2.0, 1.1, 2.1]})
            dup_samples = pd.DataFrame({'Sample_ID': ['S1', 'S2'], 'Duplicated_Sample_ID': ['D1', 'D2']})
            xlsx = os.path.join(sess_dir, 'original.xlsx')
            with pd.ExcelWriter(xlsx, engine='openpyxl') as w:
                data_main.to_excel(w, sheet_name='Data', index=False)
                dup_samples.to_excel(w, sheet_name='Duplicate Samples', index=False)
                dup_data.to_excel(w, sheet_name='Duplicate_Data', index=False)
            save_session_state(sid, {'uploaded_file': 'original.xlsx', 'steps': {}})
            with self.assertRaises(ValueError):
                process_duplicate_qc(sid, source='original')
        finally:
            shutil.rmtree(sess_dir, ignore_errors=True)


import shutil  # noqa: E402

if __name__ == '__main__':
    unittest.main()

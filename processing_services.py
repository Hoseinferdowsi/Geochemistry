"""سرویس‌های پردازش قابل فراخوانی از Flask برای pipeline تحلیل زمین‌شیمی."""

import json
import os
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import seaborn as sns
from scipy.interpolate import griddata
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from sklearn.preprocessing import PowerTransformer, QuantileTransformer, StandardScaler
from sklearn.decomposition import PCA, FactorAnalysis
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, silhouette_samples

from outliers import (
    detect_outliers_dorfel,
    detect_outliers_iqr,
    detect_outliers_zscore,
)

EXCLUDED_COLUMNS = [
    'name', 'id', 'coordinates', 'Name', 'ID', 'Coordinates',
    'sample_name', 'sample_id', 'Sample', 'SampleID', 'Depth', 'depth',
]

X_KEYWORDS = [
    'x_coord', 'x_coordinate', 'easting', 'utm_x', 'longitude',
    'lon', 'x_utm', 'x utm', 'x coord',
]
Y_KEYWORDS = [
    'y_coord', 'y_coordinate', 'northing', 'utm_y', 'latitude',
    'lat', 'y_utm', 'y utm', 'y coord',
]

PIPELINE_STEPS = {
    'censored': '01_censored_processed.xlsx',
    'outliers': '02_outliers_processed.xlsx',
    'anomaly': '03_anomaly_classified.xlsx',
    'statistics': '04_column_statistics.xlsx',
    'normalization': '05_normalized_data.xlsx',
    'normalization_report': '05_normalization_report.xlsx',
    'plots': '06_plots',
    'multifactor': '07_multifactor_results.xlsx',
    'multifactor_plots': '07_multifactor_plots',
}

CENSORED_VALUE_PATTERN = re.compile(
    r'^\s*([<>])\s*(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*$'
)
ILLEGAL_EXCEL_CHARS = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]')


def get_session_dir(session_id):
    return os.path.join('sessions', session_id)


def get_session_upload_path(session_id):
    return os.path.join(get_session_dir(session_id), 'original.xlsx')


def get_session_state_path(session_id):
    return os.path.join(get_session_dir(session_id), 'pipeline_state.json')


def load_session_state(session_id):
    path = get_session_state_path(session_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'session_id': session_id,
        'original_filename': None,
        'sheet_name': None,
        'steps': {},
    }


def save_session_state(session_id, state):
    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)
    with open(get_session_state_path(session_id), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _fix_censored_value(val, left_coe, right_coe):
    """تبدیل مقادیر سنسورد مانند <0.5 یا >10 به عدد."""
    if pd.isna(val):
        return val
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return val
        match = CENSORED_VALUE_PATTERN.match(text)
        if match:
            sign, number = match.group(1), float(match.group(2))
            return number * (left_coe if sign == '<' else right_coe)
    return val


def _sanitize_for_excel(df):
    """حذف کاراکترهای غیرمجاز XML و مقادیر بی‌نهایت که باعث خطای خروجی اکسل می‌شوند."""
    sanitized = df.copy()
    sanitized = sanitized.replace([np.inf, -np.inf], np.nan)
    for col in sanitized.columns:
        if sanitized[col].dtype == object:
            sanitized[col] = sanitized[col].map(
                lambda val: ILLEGAL_EXCEL_CHARS.sub('', val) if isinstance(val, str) else val
            )
    return sanitized


def safe_to_excel(df, output_path, **kwargs):
    """ذخیره امن اکسل با openpyxl و نوشتن اتمی برای جلوگیری از فایل خراب."""
    sanitized = _sanitize_for_excel(df)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    write_kwargs = {'index': False, 'engine': 'openpyxl'}
    write_kwargs.update(kwargs)
    try:
        sanitized.to_excel(tmp_path, **write_kwargs)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _process_censored_column(series, left_coe, right_coe):
    """اصلاح مقادیر سنسورد و تبدیل ستون‌های عددی به نوع مناسب."""
    fixed = series.map(lambda val: _fix_censored_value(val, left_coe, right_coe))
    numeric = pd.to_numeric(fixed, errors='coerce')
    non_null = int(fixed.notna().sum())
    numeric_count = int(numeric.notna().sum())
    if non_null == 0:
        return fixed
    if numeric_count == 0:
        return fixed
    if numeric_count == non_null:
        return numeric
    return fixed.where(numeric.isna(), numeric)


def _count_cell_changes(before, after):
    before_norm = before.map(lambda val: '' if pd.isna(val) else str(val).strip())
    after_norm = after.map(lambda val: '' if pd.isna(val) else str(val).strip())
    return int((before_norm != after_norm).sum())


def resolve_input_path(session_id, source='auto', step_key=None):
    """تعیین فایل ورودی بر اساس مرحله قبلی pipeline یا فایل اصلی."""
    state = load_session_state(session_id)
    session_dir = get_session_dir(session_id)

    if source == 'original':
        return get_session_upload_path(session_id), 'original'

    if source == 'custom' and step_key:
        custom_path = os.path.join(session_dir, f'custom_{step_key}.xlsx')
        if os.path.exists(custom_path):
            return custom_path, 'custom'

    step_order = ['censored', 'outliers', 'anomaly', 'statistics', 'normalization']
    if source == 'auto':
        for step in reversed(step_order):
            # خود مرحله نرمال‌سازی نباید ورودی خودش باشد
            if step == step_key:
                continue
            if step in state.get('steps', {}):
                rel_path = state['steps'][step]['output_file']
                full_path = os.path.join(session_dir, rel_path)
                if os.path.exists(full_path):
                    return full_path, step
        return get_session_upload_path(session_id), 'original'

    if source in state.get('steps', {}):
        rel_path = state['steps'][source]['output_file']
        return os.path.join(session_dir, rel_path), source

    return get_session_upload_path(session_id), 'original'


def process_censored_data(session_id, sheet_name=None, left_coe=0.75, right_coe=1.25):
    state = load_session_state(session_id)
    filepath = get_session_upload_path(session_id)
    sheet_name = sheet_name or state.get('sheet_name', 'Sheet1')

    df = pd.read_excel(filepath, sheet_name=sheet_name, engine='openpyxl')
    left_coe = float(left_coe)
    right_coe = float(right_coe)
    if left_coe <= 0 or right_coe <= 0:
        raise ValueError('ضرایب تعدیل باید عدد مثبت باشند')

    excluded = [col for col in EXCLUDED_COLUMNS if col in df.columns]
    processed_df = df.copy()
    changes_count = 0

    for column in processed_df.columns:
        if column in excluded:
            continue
        original_column = df[column]
        processed_column = _process_censored_column(original_column, left_coe, right_coe)
        processed_df[column] = processed_column
        changes_count += _count_cell_changes(original_column, processed_column)

    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)
    output_rel = PIPELINE_STEPS['censored']
    output_path = os.path.join(session_dir, output_rel)
    safe_to_excel(processed_df, output_path)

    state['sheet_name'] = sheet_name
    state['steps']['censored'] = {
        'output_file': output_rel,
        'changes_count': changes_count,
        'rows': len(df),
        'cols': len(df.columns),
        'left_coe': left_coe,
        'right_coe': right_coe,
    }
    save_session_state(session_id, state)

    return {
        'changes_count': changes_count,
        'original_rows': len(df),
        'original_cols': len(df.columns),
        'output_file': output_rel,
        'left_coe': left_coe,
        'right_coe': right_coe,
    }


def process_outliers(session_id, method='iqr', threshold=3, sheet_name=None, source='auto'):
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='outliers')
    df = pd.read_excel(input_path, sheet_name=sheet_name, engine='openpyxl') if sheet_name else pd.read_excel(input_path, engine='openpyxl')
    processed_df = df.copy()
    changes_summary = {}
    total_changes = 0

    for column in processed_df.select_dtypes(include=[np.number]).columns:
        original_data = processed_df[column].copy()
        if method.lower() == 'zscore':
            outliers, replacement_values = detect_outliers_zscore(processed_df[column], threshold)
            processed_df.loc[outliers, column] = replacement_values[outliers]
        elif method.lower() == 'dorfel':
            processed_df[column] = detect_outliers_dorfel(processed_df[column].copy())
        else:
            outliers, replacement_values = detect_outliers_iqr(processed_df[column])
            processed_df.loc[outliers, column] = replacement_values[outliers]
        changes = int((original_data != processed_df[column]).sum())
        changes_summary[column] = changes
        total_changes += changes

    session_dir = get_session_dir(session_id)
    output_rel = PIPELINE_STEPS['outliers']
    output_path = os.path.join(session_dir, output_rel)
    safe_to_excel(processed_df, output_path)

    state = load_session_state(session_id)
    state['steps']['outliers'] = {
        'output_file': output_rel,
        'method': method,
        'input_source': input_source,
        'total_changes': total_changes,
        'changes_by_column': changes_summary,
        'rows': len(df),
        'cols': len(df.columns),
    }
    save_session_state(session_id, state)

    return {
        'method': method,
        'input_source': input_source,
        'total_changes': total_changes,
        'changes_by_column': changes_summary,
        'original_rows': len(df),
        'original_cols': len(df.columns),
        'output_file': output_rel,
    }


def _boxcox_transform(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data, None
    if np.any(data_clean <= 0):
        shift = abs(np.min(data_clean)) + 0.001
        data_shifted = data_clean + shift
    else:
        data_shifted = data_clean
    try:
        transformed, lambda_val = stats.boxcox(data_shifted)
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result, lambda_val
    except Exception:
        return data, None


def _yeojohnson_transform(data):
    pt = PowerTransformer(method='yeo-johnson')
    data_clean = data[~np.isnan(data)].reshape(-1, 1)
    if len(data_clean) < 3:
        return data, None
    try:
        transformed = pt.fit_transform(data_clean).flatten()
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result, pt.lambdas_[0]
    except Exception:
        return data, None


def _quantile_normalize(data):
    qt = QuantileTransformer(output_distribution='normal', random_state=42)
    data_clean = data[~np.isnan(data)].reshape(-1, 1)
    if len(data_clean) < 3:
        return data
    try:
        transformed = qt.fit_transform(data_clean).flatten()
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result
    except Exception:
        return data


def _rank_based_normalize(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    ranks = stats.rankdata(data_clean)
    percentiles = (ranks - 0.5) / len(data_clean)
    z_scores = stats.norm.ppf(percentiles)
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = z_scores
    return result


def _log_transform(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    if np.any(data_clean <= 0):
        shift = abs(np.min(data_clean)) + 0.001
        data_shifted = data_clean + shift
    else:
        data_shifted = data_clean
    transformed = np.log(data_shifted)
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = transformed
    return result


def _sqrt_transform(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    if np.any(data_clean < 0):
        shift = abs(np.min(data_clean)) + 0.001
        data_shifted = data_clean + shift
    else:
        data_shifted = data_clean
    transformed = np.sqrt(data_shifted)
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = transformed
    return result


TRANSFORM_METHODS = {
    'Box-Cox': _boxcox_transform,
    'Yeo-Johnson': _yeojohnson_transform,
    'Quantile': _quantile_normalize,
    'Rank-Based': _rank_based_normalize,
    'Log': _log_transform,
    'Sqrt': _sqrt_transform,
}


def _shapiro_wilk_test(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return np.nan, np.nan
    if len(data_clean) > 5000:
        data_clean = np.random.choice(data_clean, 5000, replace=False)
    try:
        return stats.shapiro(data_clean)
    except Exception:
        return np.nan, np.nan


def _skewness(data):
    data_clean = data[~np.isnan(data)]
    return stats.skew(data_clean) if len(data_clean) >= 3 else np.nan


def _kurtosis(data):
    data_clean = data[~np.isnan(data)]
    return stats.kurtosis(data_clean, fisher=False) if len(data_clean) >= 3 else np.nan


def process_normalization(session_id, source='auto', methods=None, output_mode='best'):
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='normalization')
    df = pd.read_excel(input_path, engine='openpyxl')

    columns_to_transform = _get_normalization_target_columns(df, session_id=session_id)

    if not columns_to_transform:
        raise ValueError('هیچ ستون عددی قابل تبدیلی یافت نشد')

    selected_methods = methods or list(TRANSFORM_METHODS.keys())
    results = []
    best_methods = {}

    for col in columns_to_transform:
        original_data = df[col].values.copy()
        original_skew = _skewness(original_data)
        original_kurt = _kurtosis(original_data)
        _, original_pvalue = _shapiro_wilk_test(original_data)
        best_pvalue = original_pvalue
        best_method_name = 'Original'

        for method_name in selected_methods:
            if method_name not in TRANSFORM_METHODS:
                continue
            try:
                result = TRANSFORM_METHODS[method_name](original_data)
                if isinstance(result, tuple):
                    transformed_data, param = result
                    param_info = f"λ={param:.3f}" if param is not None else 'N/A'
                else:
                    transformed_data = result
                    param_info = 'N/A'

                transformed_skew = _skewness(transformed_data)
                transformed_kurt = _kurtosis(transformed_data)
                _, transformed_pvalue = _shapiro_wilk_test(transformed_data)

                results.append({
                    'Column': col,
                    'Method': method_name,
                    'Parameter': param_info,
                    'Original_Skewness': original_skew,
                    'Transformed_Skewness': transformed_skew,
                    'Original_Kurtosis': original_kurt,
                    'Transformed_Kurtosis': transformed_kurt,
                    'Original_Shapiro_pvalue': original_pvalue,
                    'Transformed_Shapiro_pvalue': transformed_pvalue,
                    'Better_Fit': (
                        transformed_pvalue > original_pvalue
                        if not np.isnan(transformed_pvalue) and not np.isnan(original_pvalue)
                        else False
                    ),
                })

                col_name_safe = f"{col}_{method_name.replace('-', '_').replace(' ', '_')}"
                df[col_name_safe] = transformed_data

                if not np.isnan(transformed_pvalue) and transformed_pvalue >= (best_pvalue or 0):
                    best_pvalue = transformed_pvalue
                    best_method_name = method_name
            except Exception:
                continue

        best_methods[col] = best_method_name

    session_dir = get_session_dir(session_id)
    data_rel = PIPELINE_STEPS['normalization']
    data_path = os.path.join(session_dir, data_rel)

    # ── ساخت شیت‌ها ──
    # شیت ۱: ستون‌های غیرعددی + مختصات + ستون‌های تبدیل‌شده
    coord_cols = _get_coordinate_columns(df, session_id=session_id)
    non_numeric_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    output_df = df[non_numeric_cols + sorted(coord_cols)].copy()
    if output_mode == 'all':
        # همه روش‌های انتخابی برای هر ستون
        for col in columns_to_transform:
            for method_name in selected_methods:
                safe_method = method_name.replace('-', '_').replace(' ', '_')
                src_col = f"{col}_{safe_method}"
                if src_col in df.columns:
                    output_df[src_col] = df[src_col]
    else:
        # فقط بهترین روش برای هر ستون (نام ستون = نام عنصر_روش)
        for col_name, best_m in best_methods.items():
            if best_m == 'Original':
                # بهترین روش اصلی است — مقدار اصلی را با نام اصلی نگه‌دار
                if col_name in df.columns:
                    output_df[col_name] = df[col_name]
            else:
                safe_method = best_m.replace('-', '_').replace(' ', '_')
                src_col = f"{col_name}_{safe_method}"
                if src_col in df.columns:
                    output_df[src_col] = df[src_col]
    sanitized_data = _sanitize_for_excel(output_df)
    # شیت ۲: گزارش تفصیلی نتایج
    report_df = pd.DataFrame(results)
    if not report_df.empty:
        report_df = report_df.rename(columns={
            'Column': 'ستون', 'Method': 'روش', 'Parameter': 'پارامتر',
            'Original_Skewness': 'چولگی اصلی', 'Transformed_Skewness': 'چولگی تبدیل\u200cشده',
            'Original_Kurtosis': 'کشیدگی اصلی', 'Transformed_Kurtosis': 'کشیدگی تبدیل\u200cشده',
            'Original_Shapiro_pvalue': 'p-value شاپیرو اصلی', 'Transformed_Shapiro_pvalue': 'p-value شاپیرو تبدیل\u200cشده',
            'Better_Fit': 'بهبود توزیع',
        })
        report_df['بهبود توزیع'] = report_df['بهبود توزیع'].map({True: 'بله', False: 'خیر'})
    # شیت ۳: خلاصه بهترین روش برای هر ستون
    summary_rows = []
    for col_name, best_m in best_methods.items():
        original_data = None
        for r in results:
            if r['Column'] == col_name and r['Method'] == best_m:
                original_data = r
                break
        summary_rows.append({
            'ستون': col_name,
            'بهترین روش': best_m,
            'پارامتر': original_data['Parameter'] if original_data else 'N/A',
            'p-value شاپیرو (اصلی)': round(original_data['Original_Shapiro_pvalue'], 6) if original_data and not np.isnan(original_data['Original_Shapiro_pvalue']) else 'N/A',
            'p-value شاپیرو (تبدیل\u200cشده)': round(original_data['Transformed_Shapiro_pvalue'], 6) if original_data and not np.isnan(original_data['Transformed_Shapiro_pvalue']) else 'N/A',
            'چولگی (اصلی)': round(original_data['Original_Skewness'], 4) if original_data and not np.isnan(original_data['Original_Skewness']) else 'N/A',
            'چولگی (تبدیل\u200cشده)': round(original_data['Transformed_Skewness'], 4) if original_data and not np.isnan(original_data['Transformed_Skewness']) else 'N/A',
        })
    summary_df = pd.DataFrame(summary_rows)

    # ذخیره فایل اکسل چندشیته‌ای
    output_path = Path(data_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            sanitized_data.to_excel(writer, sheet_name='داده‌های تبدیل\u200cشده', index=False)
            report_df.to_excel(writer, sheet_name='گزارش تفصیلی', index=False)
            summary_df.to_excel(writer, sheet_name='خلاصه بهترین روش', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    state = load_session_state(session_id)
    state['steps']['normalization'] = {
        'output_file': data_rel,
        'input_source': input_source,
        'analyzed_columns': len(columns_to_transform),
        'selected_methods': selected_methods,
        'best_methods': best_methods,
        'output_mode': output_mode,
    }
    save_session_state(session_id, state)

    return {
        'input_source': input_source,
        'analyzed_columns': len(columns_to_transform),
        'selected_methods': selected_methods,
        'best_methods': best_methods,
        'output_file': data_rel,
        'results_count': len(results),
        'output_mode': output_mode,
    }


def _get_coordinate_columns(df, session_id=None):
    """شناسایی ستون‌های مختصات بر اساس نام ستون یا انتخاب کاربر."""
    # اگر کاربر ستون‌ها را انتخاب کرده باشد، از آن‌ها استفاده کن
    if session_id:
        state = load_session_state(session_id)
        user_x = state.get('user_x_col')
        user_y = state.get('user_y_col')
        user_cols = set()
        if user_x and user_x in df.columns:
            user_cols.add(user_x)
        if user_y and user_y in df.columns:
            user_cols.add(user_y)
        if user_cols:
            return user_cols
    return {
        col for col in df.columns
        if any(k in str(col).lower().strip() for k in X_KEYWORDS + Y_KEYWORDS)
    }


# پسوندهای ستون‌های تبدیل‌شده قبلی — برای حذف از لیست ورودی
_NORM_TRANSFORM_SUFFIXES = [
    '_Box_Cox', '_Yeo_Johnson', '_Quantile', '_Rank_Based', '_Log', '_Sqrt',
]


def _get_normalization_target_columns(df, session_id=None):
    """ستون‌های عددی قابل تبدیل؛ بدون ستون‌های شناسه، متنی، مختصات و تبدیل‌شده‌های قبلی."""
    excluded = {col for col in EXCLUDED_COLUMNS if col in df.columns}
    excluded.update(_get_coordinate_columns(df, session_id=session_id))
    numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
    # حذف ستون‌هایی که قبلاً تبدیل شده‌اند (پسوند _Method دارند)
    return [
        col for col in numeric_columns
        if col not in excluded and not any(col.endswith(s) for s in _NORM_TRANSFORM_SUFFIXES)
    ]


def _identify_coordinate_columns(df, session_id=None):
    """شناسایی ستون‌های X و Y: اولویت با انتخاب کاربر، سپس شناسایی خودکار."""
    # اگر کاربر ستون‌ها را انتخاب کرده باشد
    if session_id:
        state = load_session_state(session_id)
        user_x = state.get('user_x_col')
        user_y = state.get('user_y_col')
        if user_x and user_x in df.columns and user_y and user_y in df.columns:
            return user_x, user_y
        # اگر فقط یکی انتخاب شده، دیگری را خودکار شناسایی کن
        if user_x and user_x in df.columns:
            x_col = user_x
            y_col = None
            for col in df.columns:
                if col != x_col and any(k in str(col).lower().strip() for k in Y_KEYWORDS):
                    y_col = col
                    break
            if y_col is None:
                for col in df.columns:
                    if col != x_col:
                        y_col = col
                        break
            return x_col, y_col
        if user_y and user_y in df.columns:
            y_col = user_y
            x_col = None
            for col in df.columns:
                if col != y_col and any(k in str(col).lower().strip() for k in X_KEYWORDS):
                    x_col = col
                    break
            if x_col is None:
                for col in df.columns:
                    if col != y_col:
                        x_col = col
                        break
            return x_col, y_col
    # شناسایی خودکار (روش قبلی)
    x_col = y_col = None
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if x_col is None and any(k in col_lower for k in X_KEYWORDS):
            x_col = col
        if y_col is None and any(k in col_lower for k in Y_KEYWORDS):
            y_col = col
    if x_col is None:
        x_col = df.columns[0]
    if y_col is None and len(df.columns) > 1:
        y_col = df.columns[1]
    return x_col, y_col


def _idw_interpolation(x, y, values, grid_size=100, power=2):
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean, y_clean, values_clean = x[mask], y[mask], values[mask]
    if len(x_clean) < 4:
        return None, None, None

    x_min, x_max = x_clean.min(), x_clean.max()
    y_min, y_max = y_clean.min(), y_clean.max()
    x_pad = (x_max - x_min) * 0.05
    y_pad = (y_max - y_min) * 0.05
    xi = np.linspace(x_min - x_pad, x_max + x_pad, grid_size)
    yi = np.linspace(y_min - y_pad, y_max + y_pad, grid_size)
    xi, yi = np.meshgrid(xi, yi)
    zi = np.zeros_like(xi)
    for i in range(grid_size):
        for j in range(grid_size):
            distances = np.sqrt((xi[i, j] - x_clean) ** 2 + (yi[i, j] - y_clean) ** 2)
            weights = 1.0 / (distances ** power + 1e-10)
            weights_sum = weights.sum()
            zi[i, j] = np.sum(values_clean * weights) / weights_sum if weights_sum > 0 else np.nan
    return xi, yi, zi


def _create_grid(x, y, values, grid_size=100, method='linear'):
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean, y_clean, values_clean = x[mask], y[mask], values[mask]
    if len(x_clean) < 4:
        return None, None, None
    x_min, x_max = x_clean.min(), x_clean.max()
    y_min, y_max = y_clean.min(), y_clean.max()
    x_pad = (x_max - x_min) * 0.05
    y_pad = (y_max - y_min) * 0.05
    xi = np.linspace(x_min - x_pad, x_max + x_pad, grid_size)
    yi = np.linspace(y_min - y_pad, y_max + y_pad, grid_size)
    xi, yi = np.meshgrid(xi, yi)
    try:
        zi = griddata((x_clean, y_clean), values_clean, (xi, yi), method=method)
    except Exception:
        zi = griddata((x_clean, y_clean), values_clean, (xi, yi), method='nearest')
    return xi, yi, zi


def _plot_element_map(x, y, values, element_name, output_dir, xi, yi, zi, cmap='viridis', method_name='IDW'):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean, y_clean, values_clean = x[mask], y[mask], values[mask]
    vmin = np.nanpercentile(values_clean, 5)
    vmax = np.nanpercentile(values_clean, 95)
    if vmin == vmax:
        vmin, vmax = values_clean.min(), values_clean.max()

    if xi is not None and zi is not None:
        im = axes[0].contourf(xi, yi, zi, levels=20, cmap=cmap, alpha=0.9)
        plt.colorbar(im, ax=axes[0], label=f'{element_name}')
        axes[0].scatter(x_clean, y_clean, c=values_clean, s=30, edgecolor='black', linewidth=0.5, cmap=cmap, zorder=5)
        axes[0].set_title(f'{element_name} - {method_name}')
        axes[0].grid(True, alpha=0.3)

    sizes = 20 + 80 * (values_clean - values_clean.min()) / (values_clean.max() - values_clean.min() + 1e-10)
    scat = axes[1].scatter(x_clean, y_clean, s=sizes, c=values_clean, cmap=cmap, edgecolor='black', linewidth=0.5, alpha=0.7)
    plt.colorbar(scat, ax=axes[1], label=f'{element_name}')
    axes[1].set_title(f'{element_name} - Sample Locations')
    axes[1].grid(True, alpha=0.3)
    plt.suptitle(f'Distribution Map of {element_name}', fontsize=14, fontweight='bold')
    plt.tight_layout()
    safe_name = re.sub(r'[^\w\-]', '_', str(element_name))
    output_path = Path(output_dir) / f'{safe_name}_map.png'
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()
    return output_path.name


def process_plots(session_id, source='auto', interpolation='idw', cmap='viridis', elements=None):
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='plots')
    df = pd.read_excel(input_path, engine='openpyxl')
    x_col, y_col = _identify_coordinate_columns(df, session_id=session_id)
    df = df.dropna(subset=[x_col, y_col])
    x_coords = df[x_col].values
    y_coords = df[y_col].values

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    element_cols = [col for col in numeric_cols if col not in [x_col, y_col]]
    elements_to_plot = [e for e in (elements or element_cols) if e in element_cols]
    if not elements_to_plot:
        raise ValueError('هیچ عنصر معتبری برای رسم یافت نشد')

    session_dir = get_session_dir(session_id)
    plots_rel = PIPELINE_STEPS['plots']
    plots_dir = os.path.join(session_dir, plots_rel)
    os.makedirs(plots_dir, exist_ok=True)

    generated = []
    for element in elements_to_plot:
        values = df[element].values
        if np.sum(~np.isnan(values)) < 4:
            continue
        if interpolation == 'idw':
            xi, yi, zi = _idw_interpolation(x_coords, y_coords, values)
            method_name = 'IDW'
        else:
            xi, yi, zi = _create_grid(x_coords, y_coords, values, method=interpolation)
            method_name = interpolation.capitalize()
        try:
            filename = _plot_element_map(
                x_coords, y_coords, values, element, plots_dir,
                xi, yi, zi, cmap=cmap, method_name=method_name,
            )
            generated.append(filename)
        except Exception:
            continue

    if len(generated) >= 2:
        corr_matrix = df[elements_to_plot].corr()
        plt.figure(figsize=(12, 10))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r', center=0, square=True)
        plt.title('Element Correlation Heatmap')
        plt.tight_layout()
        heatmap_name = 'correlation_heatmap.png'
        plt.savefig(os.path.join(plots_dir, heatmap_name), dpi=200, bbox_inches='tight')
        plt.close()
        generated.append(heatmap_name)

    state = load_session_state(session_id)
    state['steps']['plots'] = {
        'output_dir': plots_rel,
        'input_source': input_source,
        'generated_files': generated,
        'x_column': x_col,
        'y_column': y_col,
        'count': len(generated),
    }
    save_session_state(session_id, state)

    return {
        'input_source': input_source,
        'generated_files': generated,
        'count': len(generated),
        'output_dir': plots_rel,
        'x_column': x_col,
        'y_column': y_col,
    }


# ==================================================
# Anomaly Separation
# ==================================================


def _detect_anomalies_classical(data, threshold=2):
    """روش کلاسیک: Mean ± n × SD"""
    clean_data = data[~np.isnan(data)]
    if len(clean_data) < 4:
        return np.array([], dtype=bool), np.nan
    mean = np.mean(clean_data)
    std = np.std(clean_data)
    upper_limit = mean + threshold * std
    lower_limit = mean - threshold * std
    anomaly_mask = (data > upper_limit) | (data < lower_limit)
    return anomaly_mask, upper_limit


def _detect_anomalies_boxplot(data, multiplier=1.5):
    """روش جعبه‌ای: Q1 - k×IQR, Q3 + k×IQR"""
    clean_data = data[~np.isnan(data)]
    if len(clean_data) < 4:
        return np.array([], dtype=bool), np.nan
    q1 = np.percentile(clean_data, 25)
    q3 = np.percentile(clean_data, 75)
    iqr = q3 - q1
    lower_limit = q1 - multiplier * iqr
    upper_limit = q3 + multiplier * iqr
    anomaly_mask = (data > upper_limit) | (data < lower_limit)
    return anomaly_mask, upper_limit


def _detect_anomalies_fractal(data, target_percent=10):
    """روش فرکتالی: Concentration-Number (C-N)"""
    clean_data = data[~np.isnan(data)]
    if len(clean_data) < 10:
        return np.array([], dtype=bool), np.nan
    
    # ایجاد هیستوگرام
    min_bins = min(20, len(clean_data) // 2)
    hist, bin_edges = np.histogram(clean_data, bins=max(min_bins, 5))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    cumulative_counts = np.cumsum(hist[::-1])[::-1]
    
    # حذف bins با تعداد صفر
    mask = cumulative_counts > 0
    if sum(mask) < 5:
        return np.array([], dtype=bool), np.nan
    
    log_concentration = np.log10(bin_centers[mask])
    log_cumulative = np.log10(cumulative_counts[mask])
    
    # یافتن نقطه شکست
    n = len(log_concentration)
    min_segment = max(3, n // 5)
    best_break = None
    best_r2 = -np.inf
    
    for i in range(min_segment, n - min_segment):
        x1, y1 = log_concentration[:i], log_cumulative[:i]
        x2, y2 = log_concentration[i:], log_cumulative[i:]
        if len(x1) < 2 or len(x2) < 2:
            continue
        slope1, intercept1, r1, _, _ = stats.linregress(x1, y1)
        slope2, intercept2, r2, _, _ = stats.linregress(x2, y2)
        r2_combined = (r1**2 * len(x1) + r2**2 * len(x2)) / n
        if r2_combined > best_r2:
            best_r2 = r2_combined
            best_break = i
    
    if best_break is not None:
        # آستانه از نقطه شکست
        anomaly_threshold = 10 ** log_concentration[best_break]
    else:
        # استفاده از درصد
        sorted_data = np.sort(clean_data)
        percentile_idx = int(len(sorted_data) * (100 - target_percent) / 100)
        anomaly_threshold = sorted_data[min(percentile_idx, len(sorted_data) - 1)]
    
    anomaly_mask = data > anomaly_threshold
    return anomaly_mask, anomaly_threshold


def _anomaly_class_label(k, n_anom):
    """برچسب کلاس آنومالی k (از ۱ تا n_anom): خفیف تا شدید"""
    if n_anom <= 1:
        return 'آنومالی'
    if k == 1:
        return 'خفیف'
    if k == n_anom:
        return 'شدید'
    return f'متوسط {k}'


def process_anomaly_separation(session_id, method='classical',
                                 num_classes=3, thresholds=None,
                                 light_threshold=2, strong_threshold=3,
                                 light_multiplier=1.5, strong_multiplier=3,
                                 light_percent=15, strong_percent=5,
                                 source='auto'):
    """طبقه‌بندی آنومالی با تعداد کلاس دلخواه (۲ تا ۱۰):
    کلاس ۰ = زمینه، کلاس‌های ۱ تا n-1 = آنومالی از خفیف تا شدید
    خروجی: فایل اکسل با ستون‌های خام + ستون {col}_class براي هر عنصر"""

    num_classes = max(2, min(int(num_classes or 3), 10))
    n_anom = num_classes - 1  # تعداد کلاس‌های آنومالی

    # ── پارامتر (ضریب/درصد/آستانه) هر کلاس آنومالی ──
    params = []
    if thresholds:
        try:
            params = [float(t) for t in thresholds if t is not None]
        except (TypeError, ValueError):
            params = []
    if not params:
        # مقادیر پیش‌فرض بین خفیف و شدید تقسیم می‌شوند
        if method == 'boxplot':
            base, span = light_multiplier, strong_multiplier - light_multiplier
        elif method == 'fractal':
            base, span = light_percent, strong_percent - light_percent
        else:
            base, span = light_threshold, strong_threshold - light_threshold
        step_val = span / max(n_anom - 1, 1)
        params = [base + step_val * i for i in range(n_anom)]
    params = params[:n_anom]
    while len(params) < n_anom:
        params.append(params[-1])

    input_path, input_source = resolve_input_path(session_id, source=source, step_key='anomaly')
    df = pd.read_excel(input_path, engine='openpyxl')
    
    # شناسایی ستون‌های عددی
    excluded = {col for col in EXCLUDED_COLUMNS if col in df.columns}
    coord_cols = _get_coordinate_columns(df, session_id=session_id)
    excluded.update(coord_cols)
    numeric_cols = [col for col in df.select_dtypes(include=[np.number]).columns if col not in excluded]
    
    if not numeric_cols:
        raise ValueError('هیچ ستون عددی برای تحلیل یافت نشد')
    
    anomaly_details = []
    total_anomalies = 0
    output_df = df.copy()
    # لیست ستون‌ها با ترتیب نهایی (خام + class در کنار هم)
    final_columns = []
    # ستون‌های غیرعددی اول
    for col in df.columns:
        if col not in numeric_cols:
            final_columns.append(col)
    
    method_names = {
        'classical': 'کلاسیک (Mean ± n×SD)',
        'boxplot': 'جعبه‌ای (Box Plot IQR)',
        'fractal': 'فرکتالی (Concentration-Number)',
    }
    
    for col in numeric_cols:
        data = df[col].values
        clean_data = data[~np.isnan(data)]
        if len(clean_data) < 4:
            final_columns.append(col)
            continue
        
        # ── محاسبه آستانه هر کلاس بر اساس روش ──
        mean = np.mean(clean_data)
        std = np.std(clean_data)
        q1 = np.percentile(clean_data, 25)
        q3 = np.percentile(clean_data, 75)
        iqr = q3 - q1

        entries = []  # (پارامتر، آستانه بالا، آستانه پایین)
        for p in params:
            if method == 'boxplot':
                entries.append((p, q3 + p * iqr, q1 - p * iqr))
            elif method == 'fractal':
                _, thr = _detect_anomalies_fractal(data, p)
                entries.append((p, thr, np.nan))
            else:
                entries.append((p, mean + p * std, mean - p * std))

        # مرتب‌سازی آستانه‌ها از خفیف (کوچک) تا شدید (بزرگ)
        entries = sorted([e for e in entries if not np.isnan(e[1])], key=lambda e: e[1])

        # ── کلاس‌بندی مقادیر: کلاس 0 = زمینه، 1..n = آنومالی خفیف تا شدید ──
        class_col = np.zeros(len(df), dtype=int)
        class_thresholds = []
        valid = ~np.isnan(data)
        for k, (p, upper, lower) in enumerate(entries, start=1):
            if method == 'fractal':
                # روش فرکتالی: فقط تشخیص بالا (یک‌طرفه)
                mask = valid & (data > upper)
            else:
                # روش کلاسیک و جعبه‌ای: تشخیص دوطرفه (بالا و پایین)
                mask = valid & ((data > upper) | (data < lower))
            class_col[mask] = k  # آستانه‌ها صعودی‌اند؛ بالاترین کلاس رو می‌نویسد
            class_thresholds.append(float(upper))

        output_df[col + '_class'] = class_col
        final_columns.append(col)
        final_columns.append(col + '_class')

        # ── آمار ──
        class_counts = [int(np.sum(class_col == k)) for k in range(1, n_anom + 1)]
        num_anomalies = int(np.sum(class_col > 0))
        total_anomalies += num_anomalies
        # پر کردن آستانه‌های نامعتبر (NaN) با None
        padded_thresholds = class_thresholds + [None] * (n_anom - len(class_thresholds))

        anomaly_details.append({
            'column': col,
            'count': num_anomalies,
            'class_counts': class_counts,
            'light_count': class_counts[0] if class_counts else 0,
            'strong_count': class_counts[-1] if class_counts else 0,
            'percent': round(100 * num_anomalies / len(data), 1) if len(data) > 0 else 0,
            'thresholds': padded_thresholds,
        })
    
    # مرتب‌سازی ستون‌ها: ابتدا غیرعددی، سپس هر عنصر خام + کلاسش
    output_df = output_df[final_columns]
    
    # ── شیت گزارش اطلاعات ──
    report_rows = []
    # توضیح کلاس‌ها (بر اساس تعداد انتخابی کاربر)
    class_definitions = [
        {'کلاس': 0, 'توضیح': 'زمینه (Background)', 'توضیح_انگلیسی': 'Normal / Background data'},
    ]
    for k in range(1, num_classes):
        lbl = _anomaly_class_label(k, n_anom)
        class_definitions.append({
            'کلاس': k,
            'توضیح': f'آنومالی {lbl}',
            'توضیح_انگلیسی': f'Anomaly class {k} ({lbl})',
        })
    class_df = pd.DataFrame(class_definitions)

    # تنظیمات روش جداسازی
    settings_rows = [
        {'پارامتر': 'روش جداسازی', 'مقدار': method_names.get(method, method)},
        {'پارامتر': 'تعداد کل کلاس‌ها (شامل زمینه)', 'مقدار': str(num_classes)},
        {'پارامتر': 'تعداد کل نمونه‌ها', 'مقدار': str(len(df))},
        {'پارامتر': 'تعداد عناصر تحلیل‌شده', 'مقدار': str(len(numeric_cols))},
        {'پارامتر': 'تعداد کل آنومالی‌ها', 'مقدار': str(total_anomalies)},
    ]
    param_name = {'classical': 'آستانه n', 'boxplot': 'ضریب k', 'fractal': 'درصد هدف'}.get(method, 'مقدار')
    # در روش فرکتالی درصد بیشتر = کلاس خفیف‌تر
    display_params = sorted(params, reverse=True) if method == 'fractal' else sorted(params)
    for k, p in enumerate(display_params, start=1):
        settings_rows.append({
            'پارامتر': f'{param_name} کلاس {k} ({_anomaly_class_label(k, n_anom)})',
            'مقدار': str(p),
        })
    if method == 'classical':
        settings_rows.append({'پارامتر': 'فرمول', 'مقدار': 'Mean ± n × SD'})
    elif method == 'boxplot':
        settings_rows.append({'پارامتر': 'فرمول', 'مقدار': 'Q1 - k×IQR, Q3 + k×IQR'})
    elif method == 'fractal':
        settings_rows.append({'پارامتر': 'فرمول', 'مقدار': 'Concentration-Number (Log-Log breakpoint)'})
    settings_df = pd.DataFrame(settings_rows)

    # جزئیات هر ستون (تعداد و آستانه هر کلاس به‌صورت پویا)
    detail_rows = []
    for d in anomaly_details:
        row = {'ستون': d['column'], 'تعداد آنومالی': d['count'], 'درصد (%)': d['percent']}
        for k, c in enumerate(d['class_counts'], start=1):
            row[f'کلاس {k} ({_anomaly_class_label(k, n_anom)})'] = c
        for k, t in enumerate(d['thresholds'], start=1):
            row[f'آستانه کلاس {k}'] = round(t, 4) if isinstance(t, float) else '-'
        detail_rows.append(row)
    details_df = pd.DataFrame(detail_rows)
    
    # ذخیره فایل با دو شیت
    session_dir = get_session_dir(session_id)
    anomaly_rel = PIPELINE_STEPS['anomaly']
    anomaly_path = os.path.join(session_dir, anomaly_rel)
    output_path = Path(anomaly_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        sanitized_data = _sanitize_for_excel(output_df)
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            sanitized_data.to_excel(writer, sheet_name='داده‌ها', index=False)
            settings_df.to_excel(writer, sheet_name='تنظیمات جداسازی', index=False)
            class_df.to_excel(writer, sheet_name='توضیح کلاس‌ها', index=False)
            if not details_df.empty:
                details_df.to_excel(writer, sheet_name='جزئیات هر ستون', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    
    # به‌روزرسانی state
    state = load_session_state(session_id)
    state['steps']['anomaly'] = {
        'output_file': anomaly_rel,
        'method': method,
        'num_classes': num_classes,
        'input_source': input_source,
        'total_anomalies': total_anomalies,
        'analyzed_columns': len(numeric_cols),
        'anomaly_details': anomaly_details,
    }
    save_session_state(session_id, state)

    # مجموع هر کلاس روی همه ستون‌ها
    class_totals = []
    for k in range(n_anom):
        class_totals.append(sum(
            d['class_counts'][k] for d in anomaly_details if len(d['class_counts']) > k
        ))

    return {
        'success': True,
        'method_name': method_names.get(method, method),
        'input_source': input_source,
        'num_classes': num_classes,
        'class_totals': class_totals,
        'class_labels': [_anomaly_class_label(k, n_anom) for k in range(1, n_anom + 1)],
        'total_anomalies': total_anomalies,
        'total_light': class_totals[0] if class_totals else 0,
        'total_strong': class_totals[-1] if class_totals else 0,
        'anomaly_percent': round(100 * total_anomalies / (len(df) * len(numeric_cols)), 1) if len(df) * len(numeric_cols) > 0 else 0,
        'analyzed_columns': len(numeric_cols),
        'anomaly_details': anomaly_details,
        'output_file': anomaly_rel,
    }


# ==================================================
# Column Statistics
# ==================================================

def process_column_statistics(session_id, source='auto'):
    """محاسبه آمار توصیفی کامل برای هر ستون عددی"""
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='statistics')
    df = pd.read_excel(input_path, engine='openpyxl')
    
    # شناسایی ستون‌های عددی
    excluded = {col for col in EXCLUDED_COLUMNS if col in df.columns}
    coord_cols = _get_coordinate_columns(df, session_id=session_id)
    excluded.update(coord_cols)
    numeric_cols = [col for col in df.select_dtypes(include=[np.number]).columns if col not in excluded]
    
    if not numeric_cols:
        raise ValueError('هیچ ستون عددی برای تحلیل یافت نشد')
    
    stats_rows = []
    
    for col in numeric_cols:
        data = df[col].values
        clean_data = data[~np.isnan(data)]
        if len(clean_data) < 2:
            continue
        
        # Mode (مد)
        from scipy import stats as sp_stats
        mode_result = sp_stats.mode(clean_data, keepdims=True)
        mode_val = float(mode_result.mode[0]) if len(mode_result.mode) > 0 else np.nan
        mode_count = int(mode_result.count[0]) if len(mode_result.count) > 0 else 0
        
        # Quartiles
        q1 = float(np.percentile(clean_data, 25))
        q3 = float(np.percentile(clean_data, 75))
        iqr = q3 - q1
        
        # Skewness & Kurtosis (excess) — NaN برای داده‌های ثابت
        skewness = float(sp_stats.skew(clean_data))
        kurtosis = float(sp_stats.kurtosis(clean_data))  # excess kurtosis
        if np.isnan(skewness): skewness = None
        if np.isnan(kurtosis): kurtosis = None
        
        # Percentiles
        p90 = float(np.percentile(clean_data, 90))
        p95 = float(np.percentile(clean_data, 95))
        
        n = len(clean_data)
        std_dev = float(np.std(clean_data, ddof=1)) if n > 1 else 0.0
        se = std_dev / np.sqrt(n) if n > 0 else 0.0
        
        stats_rows.append({
            'ستون': col,
            'تعداد نمونه': n,
            'تعداد NaN': int(len(data) - n),
            'حداقل (Min)': float(np.min(clean_data)),
            'حداکثر (Max)': float(np.max(clean_data)),
            'دامنه (Range)': float(np.max(clean_data) - np.min(clean_data)),
            'میانگین (Mean)': float(np.mean(clean_data)),
            'میانه (Median)': float(np.median(clean_data)),
            'مد (Mode)': mode_val,
            'تعداد مد': mode_count,
            'واریانس (Variance)': float(np.var(clean_data, ddof=1)) if n > 1 else 0.0,
            'انحراف معیار (Std)': std_dev,
            'خطای استاندارد (SE)': float(se),
            'Q1 (چارک اول)': q1,
            'Q3 (چارک سوم)': q3,
            'IQR': iqr,
            'چولگی (Skewness)': round(skewness, 4) if skewness is not None else None,
            'کشیدگی (Kurtosis)': round(kurtosis, 4) if kurtosis is not None else None,
            'صدک ۹۰ (P90)': p90,
            'صدک ۹۵ (P95)': p95,
            'نرمال بودن (Shapiro p)': round(float(sp_stats.shapiro(clean_data[:5000])[1]), 6) if n >= 3 else None,
        })
    
    # جایگزینی NaN با None برای سازگاری JSON
    for row in stats_rows:
        for k, v in row.items():
            if isinstance(v, float) and np.isnan(v):
                row[k] = None

    stats_df = pd.DataFrame(stats_rows)

    # ذخیره فایل
    session_dir = get_session_dir(session_id)
    stats_rel = PIPELINE_STEPS['statistics']
    stats_path = os.path.join(session_dir, stats_rel)
    
    safe_to_excel(stats_df, stats_path)
    
    # به‌روزرسانی state
    state = load_session_state(session_id)
    state['steps']['statistics'] = {
        'output_file': stats_rel,
        'input_source': input_source,
        'analyzed_columns': len(numeric_cols),
    }
    save_session_state(session_id, state)
    
    return {
        'success': True,
        'input_source': input_source,
        'analyzed_columns': len(numeric_cols),
        'output_file': stats_rel,
        'stats': stats_rows,
    }


# ==================================================
# Phase 1: Multifactor Analysis
# ==================================================


def _prepare_multifactor_data(session_id, source='auto'):
    """آماده‌سازی داده عددی برای تحلیل‌های چندمتغیره."""
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='multifactor')
    df = pd.read_excel(input_path, engine='openpyxl')
    excluded = {col for col in EXCLUDED_COLUMNS if col in df.columns}
    coord_cols = _get_coordinate_columns(df, session_id=session_id)
    excluded.update(coord_cols)
    numeric_cols = [col for col in df.select_dtypes(include=[np.number]).columns if col not in excluded]
    if not numeric_cols:
        raise ValueError('هیچ ستون عددی برای تحلیل چندمتغیره یافت نشد')
    df_numeric = df[numeric_cols].dropna()
    if len(df_numeric) < 3:
        raise ValueError('تعداد نمونه‌های بدون NaN کافی نیست (حداقل ۳ مورد نیاز است)')
    return df, df_numeric, numeric_cols, input_source


def process_correlation_matrix(session_id, method='pearson', source='auto', pvalue_filter=None):
    """ماتریس همبستگی با p-values و Heatmap."""
    df, df_numeric, numeric_cols, input_source = _prepare_multifactor_data(session_id, source=source)
    n = len(df_numeric)
    k = len(numeric_cols)
   
    # محاسبه ماتریس همبستگی
    if method == 'spearman':
        corr_matrix = df_numeric[numeric_cols].corr(method='spearman')
    elif method == 'kendall':
        corr_matrix = df_numeric[numeric_cols].corr(method='kendall')
    else:
        corr_matrix = df_numeric[numeric_cols].corr(method='pearson')
   
    # محاسبه p-values
    pval_matrix = pd.DataFrame(np.ones((k, k)), index=numeric_cols, columns=numeric_cols)
    for i in range(k):
        for j in range(k):
            if i != j:
                col_i = df_numeric[numeric_cols[i]].values
                col_j = df_numeric[numeric_cols[j]].values
                if method == 'spearman':
                    _, p = stats.spearmanr(col_i, col_j)
                elif method == 'kendall':
                    _, p = stats.kendalltau(col_i, col_j)
                else:
                    _, p = stats.pearsonr(col_i, col_j)
                pval_matrix.iloc[i, j] = p
   
    # فیلتر معناداری
    significant_pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            r_val = corr_matrix.iloc[i, j]
            p_val = pval_matrix.iloc[i, j]
            is_significant = p_val < (pvalue_filter or 0.05)
            if pvalue_filter is None or is_significant:
                significant_pairs.append({
                    'ستون ۱': numeric_cols[i],
                    'ستون ۲': numeric_cols[j],
                    'همبستگی': round(r_val, 4),
                    'p-value': round(p_val, 6),
                    'معنادار': 'بله' if is_significant else 'خیر',
                })
    significant_pairs.sort(key=lambda x: abs(x['همبستگی']), reverse=True)
   
    # ذخیره Heatmap
    session_dir = get_session_dir(session_id)
    plots_rel = PIPELINE_STEPS['multifactor_plots']
    plots_dir = os.path.join(session_dir, plots_rel)
    os.makedirs(plots_dir, exist_ok=True)
   
    plt.figure(figsize=(12, 10))
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r', center=0,
                square=True, linewidths=0.5, vmin=-1, vmax=1)
    plt.title(f'{method.upper()} Correlation Matrix', fontsize=14, fontweight='bold')
    plt.tight_layout()
    heatmap_name = f'correlation_{method}_heatmap.png'
    plt.savefig(os.path.join(plots_dir, heatmap_name), dpi=200, bbox_inches='tight')
    plt.close()
   
    # ذخیره فایل اکسل
    data_rel = PIPELINE_STEPS['multifactor']
    data_path = os.path.join(session_dir, data_rel)
    corr_df = corr_matrix.round(4)
    pval_df = pval_matrix.round(6)
    pairs_df = pd.DataFrame(significant_pairs)
    output_path = Path(data_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            corr_df.to_excel(writer, sheet_name=f'همبستگی_{method}', index=True)
            pval_df.to_excel(writer, sheet_name='p-values', index=True)
            if not pairs_df.empty:
                pairs_df.to_excel(writer, sheet_name='جفت‌های معنادار', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    
    state = load_session_state(session_id)
    state['steps']['multifactor_correlation'] = {
        'output_file': data_rel,
        'input_source': input_source,
        'method': method,
        'heatmap': heatmap_name,
        'analyzed_columns': k,
        'n_samples': n,
    }
    save_session_state(session_id, state)
    
    # JSON-safe correlation pairs
    corr_pairs_json = []
    for i in range(k):
        for j in range(i + 1, k):
            corr_pairs_json.append({
                'col1': numeric_cols[i], 'col2': numeric_cols[j],
                'r': round(float(corr_matrix.iloc[i, j]), 4),
                'p': round(float(pval_matrix.iloc[i, j]), 6),
            })
    
    return {
        'success': True,
        'input_source': input_source,
        'method': method,
        'analyzed_columns': k,
        'n_samples': n,
        'heatmap': heatmap_name,
        'output_file': data_rel,
        'corr_matrix': corr_matrix.round(4).to_dict(),
        'corr_pairs': corr_pairs_json,
        'significant_pairs': significant_pairs[:20],
    }


def process_pca(session_id, source='auto', n_components=None, standardize=True):
    """تحلیل مؤلفه‌های اصلی (PCA)."""
    df, df_numeric, numeric_cols, input_source = _prepare_multifactor_data(session_id, source=source)
    n_samples = len(df_numeric)
    k = len(numeric_cols)
   
    # استانداردسازی
    if standardize:
        scaler = StandardScaler()
        X = scaler.fit_transform(df_numeric[numeric_cols].values)
    else:
        X = df_numeric[numeric_cols].values
   
    # اجرای PCA با تمام مؤلفه‌ها
    max_components = min(n_samples, k)
    pca_full = PCA(n_components=max_components)
    scores_full = pca_full.fit_transform(X)
   
    eigenvalues = pca_full.explained_variance_
    explained_var = pca_full.explained_variance_ratio_
    cumulative_var = np.cumsum(explained_var)
    loadings = pca_full.components_.T * np.sqrt(eigenvalues)
   
    # انتخاب خودکار تعداد مؤلفه‌ها
    if n_components is None:
        # Kaiser criterion: Eigenvalue > 1
        n_kaiser = int(np.sum(eigenvalues > 1))
        # 70% variance criterion
        n_var70 = int(np.searchsorted(cumulative_var, 0.70) + 1)
        n_components = max(n_kaiser, 1)
    n_components = min(n_components, max_components)
   
    # نتایج نهایی با تعداد انتخابی
    pca = PCA(n_components=n_components)
    scores = pca.fit_transform(X)
    loadings_final = pca.components_.T * np.sqrt(pca.explained_variance_)
    loadings_df = pd.DataFrame(loadings_final, index=numeric_cols,
                                columns=[f'PC{i+1}' for i in range(n_components)])
    scores_df = pd.DataFrame(scores, columns=[f'PC{i+1}' for i in range(n_components)])
    eigen_df = pd.DataFrame({
        'مؤلفه': [f'PC{i+1}' for i in range(max_components)],
        'مقدار ویژه': [round(float(e), 4) for e in eigenvalues],
        'درصد واریانس': [round(float(v) * 100, 2) for v in explained_var],
        'واریانس تجمعی (%)': [round(float(v) * 100, 2) for v in cumulative_var],
    })
    contrib_data = {'ستون': numeric_cols}
    for pc_idx in range(n_components):
        contrib_data[f'PC{pc_idx+1} Contribution (%)'] = [
            round(float(loadings_df.iloc[row_idx, pc_idx] ** 2 / n_components * 100), 2)
            for row_idx in range(k)
        ]
    contribution_df = pd.DataFrame(contrib_data)
    
    # نمودارها
    session_dir = get_session_dir(session_id)
    plots_rel = PIPELINE_STEPS['multifactor_plots']
    plots_dir = os.path.join(session_dir, plots_rel)
    os.makedirs(plots_dir, exist_ok=True)
    generated_plots = []
   
    # 1. Scree Plot
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.bar(range(1, max_components + 1), explained_var * 100, alpha=0.7, label='Individual', color='steelblue')
    ax1.plot(range(1, max_components + 1), cumulative_var * 100, 'ro-', label='Cumulative')
    ax1.axhline(y=70, color='gray', linestyle='--', alpha=0.5, label='70% threshold')
    ax1.set_xlabel('Principal Component')
    ax1.set_ylabel('Explained Variance (%)')
    ax1.set_title('Scree Plot - PCA', fontsize=14, fontweight='bold')
    ax1.set_xticks(range(1, max_components + 1))
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    plt.tight_layout()
    scree_name = 'pca_scree_plot.png'
    plt.savefig(os.path.join(plots_dir, scree_name), dpi=200, bbox_inches='tight')
    plt.close()
    generated_plots.append(scree_name)
    
    # 2. Biplot (if >= 2 components)
    if n_components >= 2:
        fig, ax = plt.subplots(figsize=(12, 10))
        ax.scatter(scores[:, 0], scores[:, 1], alpha=0.5, s=30, c='steelblue', edgecolors='black', linewidth=0.3)
        for idx, col in enumerate(numeric_cols):
            ax.annotate('', xy=(loadings_final[idx, 0] * 3, loadings_final[idx, 1] * 3),
                       xytext=(0, 0), arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
            ax.text(loadings_final[idx, 0] * 3.2, loadings_final[idx, 1] * 3.2, col,
                   fontsize=9, color='red', fontweight='bold')
        ax.set_xlabel(f'PC1 ({explained_var[0]*100:.1f}%)')
        ax.set_ylabel(f'PC2 ({explained_var[1]*100:.1f}%)')
        ax.set_title('PCA Biplot', fontsize=14, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.3)
        ax.axvline(x=0, color='gray', linestyle='--', alpha=0.3)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        biplot_name = 'pca_biplot.png'
        plt.savefig(os.path.join(plots_dir, biplot_name), dpi=200, bbox_inches='tight')
        plt.close()
        generated_plots.append(biplot_name)
    
    # 3. Loading Plot
    fig, ax = plt.subplots(figsize=(10, 8))
    if n_components >= 2:
        ax.scatter(loadings_final[:, 0], loadings_final[:, 1], s=60, c='darkblue', zorder=5)
        for idx, col in enumerate(numeric_cols):
            ax.annotate(col, (loadings_final[idx, 0], loadings_final[idx, 1]),
                       fontsize=9, fontweight='bold', ha='center', va='bottom')
        ax.set_xlabel(f'PC1 Loading')
        ax.set_ylabel(f'PC2 Loading')
    else:
        ax.barh(numeric_cols, loadings_final[:, 0], color='steelblue')
        ax.set_xlabel('PC1 Loading')
    ax.set_title('PCA Loadings Plot', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    loading_plot_name = 'pca_loadings_plot.png'
    plt.savefig(os.path.join(plots_dir, loading_plot_name), dpi=200, bbox_inches='tight')
    plt.close()
    generated_plots.append(loading_plot_name)
    
    # ذخیره فایل اکسل
    data_rel = PIPELINE_STEPS['multifactor']
    data_path = os.path.join(session_dir, data_rel)
    output_path = Path(data_path)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            eigen_df.to_excel(writer, sheet_name='Eigenvalues', index=False)
            loadings_df.round(4).to_excel(writer, sheet_name='Loadings', index=True)
            scores_df.round(4).to_excel(writer, sheet_name='Scores', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    
    state = load_session_state(session_id)
    state['steps']['multifactor_pca'] = {
        'output_file': data_rel,
        'input_source': input_source,
        'n_components': n_components,
        'n_samples': n_samples,
        'generated_plots': generated_plots,
    }
    save_session_state(session_id, state)
    
    eigen_dict = eigen_df.to_dict(orient='records')
    loadings_dict = {col: {f'PC{j+1}': round(float(loadings_df.iloc[i, j]), 4)
                           for j in range(n_components)}
                     for i, col in enumerate(numeric_cols)}
    
    return {
        'success': True,
        'input_source': input_source,
        'n_components': n_components,
        'n_samples': n_samples,
        'output_file': data_rel,
        'generated_plots': generated_plots,
        'eigenvalues': eigen_dict,
        'loadings': loadings_dict,
        'cumulative_variance': [round(float(v) * 100, 2) for v in cumulative_var],
    }


def process_hierarchical_clustering(session_id, source='auto', n_clusters=3, linkage_method='ward',
                                     distance_metric='euclidean'):
    """خوشه‌بندی سلسله‌مراتبی با Dendrogram."""
    df, df_numeric, numeric_cols, input_source = _prepare_multifactor_data(session_id, source=source)
    n_samples = len(df_numeric)
   
    scaler = StandardScaler()
    X = scaler.fit_transform(df_numeric[numeric_cols].values)
    
    # خوشه‌بندی سلسله‌مراتبی
    Z = linkage(X, method=linkage_method, metric=distance_metric)
    cluster_labels = fcluster(Z, t=n_clusters, criterion='maxclust')
    
    # محاسبه silhouette
    sil_score = silhouette_score(X, cluster_labels) if n_clusters > 1 and n_clusters < n_samples else None
    
    # آمار خوشه‌ها
    cluster_stats = []
    for c in range(1, n_clusters + 1):
        mask = cluster_labels == c
        cluster_stats.append({
            'خوشه': f'Cluster {c}',
            'تعداد نمونه': int(np.sum(mask)),
            'درصد': round(100 * np.sum(mask) / n_samples, 1),
        })
    
    # نمودار Dendrogram
    session_dir = get_session_dir(session_id)
    plots_rel = PIPELINE_STEPS['multifactor_plots']
    plots_dir = os.path.join(session_dir, plots_rel)
    os.makedirs(plots_dir, exist_ok=True)
    generated_plots = []
    
    fig, ax = plt.subplots(figsize=(14, 7))
    dendrogram(Z, labels=df_numeric.index.tolist(), ax=ax, leaf_font_size=7,
               color_threshold=Z[-(n_clusters-1), 2] if n_clusters > 1 else None)
    ax.set_title(f'Hierarchical Clustering Dendrogram ({linkage_method})', fontsize=14, fontweight='bold')
    ax.set_xlabel('Sample Index')
    ax.set_ylabel('Distance')
    plt.tight_layout()
    dendro_name = f'hierarchical_dendrogram_{linkage_method}.png'
    plt.savefig(os.path.join(plots_dir, dendro_name), dpi=200, bbox_inches='tight')
    plt.close()
    generated_plots.append(dendro_name)
    
    # ذخیره فایل اکسل
    data_rel = PIPELINE_STEPS['multifactor']
    data_path = os.path.join(session_dir, data_rel)
    cluster_df = pd.DataFrame({'نمونه': df_numeric.index.tolist(),
                                'خوشه': [f'Cluster {c}' for c in cluster_labels]})
    stats_df = pd.DataFrame(cluster_stats)
    output_path = Path(data_path)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            cluster_df.to_excel(writer, sheet_name='خوشه‌بندی سلسله‌مراتبی', index=False)
            stats_df.to_excel(writer, sheet_name='آمار خوشه‌ها', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    
    state = load_session_state(session_id)
    state['steps']['multifactor_hierarchical'] = {
        'output_file': data_rel,
        'input_source': input_source,
        'n_clusters': n_clusters,
        'linkage_method': linkage_method,
        'silhouette_score': round(sil_score, 4) if sil_score is not None else None,
        'generated_plots': generated_plots,
    }
    save_session_state(session_id, state)
    
    return {
        'success': True,
        'input_source': input_source,
        'n_clusters': n_clusters,
        'linkage_method': linkage_method,
        'distance_metric': distance_metric,
        'silhouette_score': round(sil_score, 4) if sil_score is not None else None,
        'cluster_stats': cluster_stats,
        'n_samples': n_samples,
        'output_file': data_rel,
        'generated_plots': generated_plots,
    }


def process_kmeans(session_id, source='auto', n_clusters=3, max_iter=300, n_init=10):
    """خوشه‌بندی K-Means با Elbow و Silhouette."""
    df, df_numeric, numeric_cols, input_source = _prepare_multifactor_data(session_id, source=source)
    n_samples = len(df_numeric)
   
    scaler = StandardScaler()
    X = scaler.fit_transform(df_numeric[numeric_cols].values)
   
    # K-Means
    kmeans = KMeans(n_clusters=n_clusters, max_iter=max_iter, n_init=n_init, random_state=42)
    labels = kmeans.fit_predict(X)
    centers = kmeans.cluster_centers_
    inertia = kmeans.inertia_
    sil = silhouette_score(X, labels) if n_clusters > 1 and n_clusters < n_samples else None
   
    # Elbow: تست k=2 تا min(10, n_samples-1)
    max_k = min(10, n_samples - 1)
    k_range = list(range(2, max_k + 1))
    inertias = []
    sil_scores = []
    for k_val in k_range:
        km = KMeans(n_clusters=k_val, n_init=n_init, random_state=42)
        lb = km.fit_predict(X)
        inertias.append(round(float(km.inertia_), 2))
        sil_scores.append(round(float(silhouette_score(X, lb)), 4) if k_val < n_samples else 0)
    
    # آمار خوشه‌ها
    cluster_stats = []
    for c in range(n_clusters):
        mask = labels == c
        means = {col: round(float(np.mean(df_numeric.loc[mask, col])), 4) for col in numeric_cols}
        cluster_stats.append({
            'خوشه': f'Cluster {c + 1}',
            'تعداد نمونه': int(np.sum(mask)),
            'درصد': round(100 * np.sum(mask) / n_samples, 1),
            **means,
        })
    
    # نمودارها
    session_dir = get_session_dir(session_id)
    plots_rel = PIPELINE_STEPS['multifactor_plots']
    plots_dir = os.path.join(session_dir, plots_rel)
    os.makedirs(plots_dir, exist_ok=True)
    generated_plots = []
    
    # Elbow Plot
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(k_range, inertias, 'bo-', linewidth=2, markersize=8, label='Inertia')
    ax1.set_xlabel('Number of Clusters (K)')
    ax1.set_ylabel('Inertia (Within-Cluster SS)', color='blue')
    ax2 = ax1.twinx()
    ax2.plot(k_range, sil_scores, 'rs-', linewidth=2, markersize=8, label='Silhouette')
    ax2.set_ylabel('Silhouette Score', color='red')
    ax1.set_title('K-Means: Elbow & Silhouette Plot', fontsize=14, fontweight='bold')
    ax1.set_xticks(k_range)
    ax1.grid(True, alpha=0.3)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='best')
    plt.tight_layout()
    elbow_name = 'kmeans_elbow_silhouette.png'
    plt.savefig(os.path.join(plots_dir, elbow_name), dpi=200, bbox_inches='tight')
    plt.close()
    generated_plots.append(elbow_name)
    
    # Cluster Scatter (if >= 2 numeric cols)
    if len(numeric_cols) >= 2:
        fig, ax = plt.subplots(figsize=(10, 8))
        colors = plt.cm.Set2(np.linspace(0, 1, n_clusters))
        for c in range(n_clusters):
            mask = labels == c
            ax.scatter(df_numeric.loc[mask, numeric_cols[0]], df_numeric.loc[mask, numeric_cols[1]],
                      c=[colors[c]], label=f'Cluster {c+1}', s=40, alpha=0.7, edgecolors='black', linewidth=0.3)
        ax.scatter(centers[:, 0], centers[:, 1], c='black', marker='X', s=200, linewidths=2, label='Centroids')
        ax.set_xlabel(numeric_cols[0])
        ax.set_ylabel(numeric_cols[1])
        ax.set_title(f'K-Means Clustering (K={n_clusters})', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        scatter_name = 'kmeans_cluster_scatter.png'
        plt.savefig(os.path.join(plots_dir, scatter_name), dpi=200, bbox_inches='tight')
        plt.close()
        generated_plots.append(scatter_name)
    
    # ذخیره فایل اکسل
    data_rel = PIPELINE_STEPS['multifactor']
    data_path = os.path.join(session_dir, data_rel)
    cluster_df = pd.DataFrame({'نمونه': df_numeric.index.tolist(),
                                'خوشه': [f'Cluster {c+1}' for c in labels]})
    elbow_df = pd.DataFrame({'K': k_range, 'Inertia': inertias, 'Silhouette': sil_scores})
    stats_df = pd.DataFrame(cluster_stats)
    output_path = Path(data_path)
    tmp_path = output_path.with_name(f'{output_path.stem}.tmp{output_path.suffix}')
    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            cluster_df.to_excel(writer, sheet_name='خوشه‌بندی K-Means', index=False)
            stats_df.to_excel(writer, sheet_name='آمار خوشه‌ها', index=False)
            elbow_df.to_excel(writer, sheet_name='Elbow Data', index=False)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    
    state = load_session_state(session_id)
    state['steps']['multifactor_kmeans'] = {
        'output_file': data_rel,
        'input_source': input_source,
        'n_clusters': n_clusters,
        'inertia': round(float(inertia), 2),
        'silhouette_score': round(sil, 4) if sil is not None else None,
        'generated_plots': generated_plots,
    }
    save_session_state(session_id, state)
    
    return {
        'success': True,
        'input_source': input_source,
        'n_clusters': n_clusters,
        'n_samples': n_samples,
        'inertia': round(float(inertia), 2),
        'silhouette_score': round(sil, 4) if sil is not None else None,
        'cluster_stats': cluster_stats,
        'elbow_data': {'k': k_range, 'inertias': inertias, 'sil_scores': sil_scores},
        'output_file': data_rel,
        'generated_plots': generated_plots,
    }

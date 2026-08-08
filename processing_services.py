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
from sklearn.preprocessing import PowerTransformer, QuantileTransformer

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
    'x', 'x_coord', 'x_coordinate', 'easting', 'utm_x', 'longitude',
    'lon', 'x_utm', 'x utm', 'x coord',
]
Y_KEYWORDS = [
    'y', 'y_coord', 'y_coordinate', 'northing', 'utm_y', 'latitude',
    'lat', 'y_utm', 'y utm', 'y coord',
]

PIPELINE_STEPS = {
    'censored': '01_censored_processed.xlsx',
    'outliers': '02_outliers_processed.xlsx',
    'normalization': '03_normalized_data.xlsx',
    'normalization_report': '03_normalization_report.xlsx',
    'plots': '04_plots',
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
    """تبدیل مقادیر سانسور شده مانند <0.5 یا >10 به عدد."""
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
    """اصلاح مقادیر سانسور شده و تبدیل ستون‌های عددی به نوع مناسب."""
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

    step_order = ['censored', 'outliers', 'normalization']
    if source == 'auto':
        for step in reversed(step_order):
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


def process_normalization(session_id, source='auto', methods=None):
    input_path, input_source = resolve_input_path(session_id, source=source, step_key='normalization')
    df = pd.read_excel(input_path, engine='openpyxl')

    columns_to_transform = _get_normalization_target_columns(df)

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

                col_name_safe = f"{col}_transformed_{method_name.replace('-', '_').replace(' ', '_')}"
                df[col_name_safe] = transformed_data

                if not np.isnan(transformed_pvalue) and transformed_pvalue >= (best_pvalue or 0):
                    best_pvalue = transformed_pvalue
                    best_method_name = method_name
            except Exception:
                continue

        best_methods[col] = best_method_name

    session_dir = get_session_dir(session_id)
    data_rel = PIPELINE_STEPS['normalization']
    report_rel = PIPELINE_STEPS['normalization_report']
    data_path = os.path.join(session_dir, data_rel)
    report_path = os.path.join(session_dir, report_rel)
    safe_to_excel(df, data_path)
    safe_to_excel(pd.DataFrame(results), report_path)

    state = load_session_state(session_id)
    state['steps']['normalization'] = {
        'output_file': data_rel,
        'report_file': report_rel,
        'input_source': input_source,
        'analyzed_columns': len(columns_to_transform),
        'best_methods': best_methods,
    }
    save_session_state(session_id, state)

    return {
        'input_source': input_source,
        'analyzed_columns': len(columns_to_transform),
        'best_methods': best_methods,
        'output_file': data_rel,
        'report_file': report_rel,
        'results_count': len(results),
    }


def _get_coordinate_columns(df):
    """شناسایی ستون‌های مختصات بر اساس نام ستون."""
    return {
        col for col in df.columns
        if any(k in str(col).lower().strip() for k in X_KEYWORDS + Y_KEYWORDS)
    }


def _get_normalization_target_columns(df):
    """ستون‌های عددی قابل تبدیل؛ بدون ستون‌های شناسه، متنی و مختصات."""
    excluded = {col for col in EXCLUDED_COLUMNS if col in df.columns}
    excluded.update(_get_coordinate_columns(df))
    numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
    return [col for col in numeric_columns if col not in excluded]


def _identify_coordinate_columns(df):
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
    x_col, y_col = _identify_coordinate_columns(df)
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

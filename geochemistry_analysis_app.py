from flask import Flask, render_template, request, send_file, jsonify
from flask.json.provider import DefaultJSONProvider
import os
import re
import uuid
import zipfile
import io
import math
import secrets
import shutil
import threading
import time
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename

import config
from processing_services import (
    get_session_dir,
    get_session_upload_path,
    load_session_state,
    save_session_state,
    process_censored_data,
    process_outliers,
    process_normalization,
    process_plots,
    process_duplicate_qc,
    process_anomaly_separation,
    process_column_statistics,
    process_correlation_matrix,
    process_pca,
    process_hierarchical_clustering,
    process_kmeans,
    process_factor_analysis,
    process_element_association,
    process_mahalanobis,
)


class SafeJSONProvider(DefaultJSONProvider):
    """JSON provider that converts NaN/Inf to null for valid JSON responses."""
    def dumps(self, obj, **kwargs):
        import json as _json
        def _sanitize(o):
            if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
                return None
            if isinstance(o, (np.floating,)):
                v = float(o)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
            return o
        # Recursively sanitize NaN/Inf before passing to the standard serializer
        def _deep_sanitize(o):
            if isinstance(o, float):
                return _sanitize(o)
            if isinstance(o, (np.floating, np.integer)):
                return _sanitize(o)
            if isinstance(o, dict):
                return {k: _deep_sanitize(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_deep_sanitize(v) for v in o]
            if isinstance(o, np.ndarray):
                return _deep_sanitize(o.tolist())
            return o
        sanitized = _deep_sanitize(obj)
        return super().dumps(sanitized, **kwargs)


app = Flask(__name__)
app.json_provider_class = SafeJSONProvider
app.json = SafeJSONProvider(app)
# کلید session و سایر تنظیمات از config.py (قابل بازنویسی با متغیر محیطی)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
ALLOWED_EXTENSIONS = config.ALLOWED_EXTENSIONS


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def create_session_id():
    return datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]


@app.route('/')
def index():
    return render_template('geochemistry_analysis.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'فایل انتخاب نشده است'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'فایل انتخاب نشده است'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'نوع فایل پشتیبانی نمی‌شود. فقط فایل‌های Excel مجاز هستند'}), 400

    session_id = create_session_id()
    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)

    original_name = secure_filename(file.filename)
    filepath = get_session_upload_path(session_id)

    try:
        file.save(filepath)

        import pandas as pd
        excel_file = pd.ExcelFile(filepath)
        sheet_names = excel_file.sheet_names
        default_sheet = sheet_names[0]

        # Read columns from default sheet (read first row to get headers)
        df_cols = pd.read_excel(filepath, sheet_name=default_sheet, nrows=1, engine='openpyxl')
        columns = [str(c) for c in df_cols.columns.tolist()]

        state = {
            'session_id': session_id,
            'original_filename': original_name,
            'sheet_name': default_sheet,
            'steps': {},
            'user_x_col': None,
            'user_y_col': None,
        }
        save_session_state(session_id, state)

        return jsonify({
            'success': True,
            'session_id': session_id,
            'filename': original_name,
            'sheet_names': sheet_names,
            'default_sheet': default_sheet,
            'columns': columns,
            'message': 'فایل با موفقیت آپلود شد',
        })
    except Exception as e:
        return jsonify({'error': f'خطا در آپلود فایل: {str(e)}'}), 500


@app.route('/session/<session_id>/status')
def session_status(session_id):
    session_dir = get_session_dir(session_id)
    if not os.path.exists(session_dir):
        return jsonify({'error': 'جلسه یافت نشد'}), 404
    return jsonify({'success': True, 'state': load_session_state(session_id)})


@app.route('/get_columns', methods=['POST'])
def get_columns_route():
    """برگرداندن نام ستون‌های یک شیت خاص."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        sheet_name = data.get('sheet_name')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        filepath = get_session_upload_path(session_id)
        if not os.path.exists(filepath):
            return jsonify({'error': 'فایل جلسه یافت نشد'}), 404

        import pandas as pd
        df_cols = pd.read_excel(filepath, sheet_name=sheet_name, nrows=1, engine='openpyxl')
        columns = [str(c) for c in df_cols.columns.tolist()]

        return jsonify({'success': True, 'columns': columns})
    except Exception as e:
        return jsonify({'error': f'خطا در خواندن ستون‌ها: {str(e)}'}), 500


@app.route('/save_coordinates', methods=['POST'])
def save_coordinates_route():
    """ذخیره انتخاب کاربر برای ستون‌های X و Y."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        x_col = data.get('x_col')
        y_col = data.get('y_col')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        state = load_session_state(session_id)
        state['user_x_col'] = x_col if x_col else None
        state['user_y_col'] = y_col if y_col else None
        save_session_state(session_id, state)

        return jsonify({
            'success': True,
            'message': f'ستون‌های مختصات ذخیره شدند: X={x_col or "خودکار"}, Y={y_col or "خودکار"}',
            'user_x_col': state['user_x_col'],
            'user_y_col': state['user_y_col'],
        })
    except Exception as e:
        return jsonify({'error': f'خطا در ذخیره مختصات: {str(e)}'}), 500


@app.route('/process_censored_data', methods=['POST'])
def process_censored_data_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        sheet_name = data.get('sheet_name')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        if not os.path.exists(get_session_upload_path(session_id)):
            return jsonify({'error': 'فایل جلسه یافت نشد'}), 404

        left_coe = float(data.get('left_coe', config.CENSOR_LEFT_COEFFICIENT))
        right_coe = float(data.get('right_coe', config.CENSOR_RIGHT_COEFFICIENT))
        if left_coe <= 0 or right_coe <= 0:
            return jsonify({'error': 'ضرایب تعدیل باید عدد مثبت باشند'}), 400

        result = process_censored_data(
            session_id,
            sheet_name=sheet_name,
            left_coe=left_coe,
            right_coe=right_coe,
        )
        return jsonify({
            'success': True,
            'message': 'پردازش داده‌های سنسورد با موفقیت انجام شد',
            'session_id': session_id,
            **result,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'خطا در پردازش داده‌های سنسورد: {str(e)}'}), 500


@app.route('/process_outliers', methods=['POST'])
def process_outliers_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        sheet_name = data.get('sheet_name')
        method = data.get('method', 'iqr')
        threshold = float(data.get('threshold', 3))
        source = data.get('source', 'auto')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_outliers(
            session_id, method=method, threshold=threshold,
            sheet_name=sheet_name, source=source,
        )
        return jsonify({
            'success': True,
            'message': f'پردازش مقادیر خارج از رده با روش {method} با موفقیت انجام شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در پردازش مقادیر خارج از رده: {str(e)}'}), 500


@app.route('/process_anomaly_separation', methods=['POST'])
def process_anomaly_separation_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        method = data.get('method', 'classical')
        source = data.get('source', 'auto')

        # تعداد کلاس‌ها (۲ تا ۱۰) و آستانه/ضریب/درصد هر کلاس
        try:
            num_classes = int(data.get('num_classes', 3))
        except (TypeError, ValueError):
            num_classes = 3
        raw_thresholds = data.get('thresholds')
        if isinstance(raw_thresholds, list):
            try:
                thresholds = [float(t) for t in raw_thresholds if t is not None]
            except (TypeError, ValueError):
                thresholds = []
        else:
            thresholds = []

        # مقادیر پیش‌فرض (سازگاری با نسخه قبل)
        light_threshold = float(data.get('light_threshold', data.get('threshold', 2)))
        strong_threshold = float(data.get('strong_threshold', 3))
        light_multiplier = float(data.get('light_multiplier', data.get('multiplier', 1.5)))
        strong_multiplier = float(data.get('strong_multiplier', 3))
        light_percent = float(data.get('light_percent', data.get('target_percent', 15)))
        strong_percent = float(data.get('strong_percent', 5))

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_anomaly_separation(
            session_id, method=method,
            num_classes=num_classes, thresholds=thresholds,
            light_threshold=light_threshold, strong_threshold=strong_threshold,
            light_multiplier=light_multiplier, strong_multiplier=strong_multiplier,
            light_percent=light_percent, strong_percent=strong_percent,
            source=source,
        )
        return jsonify({
            'success': True,
            'message': f'جداسازی آنومالی با روش {method} و {result.get("num_classes", num_classes)} کلاس با موفقیت انجام شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در جداسازی آنومالی: {str(e)}'}), 500


@app.route('/process_statistics', methods=['POST'])
def process_statistics_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_column_statistics(session_id, source=source)
        return jsonify({
            'success': True,
            'message': 'آمار توصیفی با موفقیت محاسبه شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در محاسبه آمار: {str(e)}'}), 500


@app.route('/process_normalization', methods=['POST'])
def process_normalization_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        methods = data.get('methods')
        output_mode = data.get('output_mode', 'best')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_normalization(session_id, source=source, methods=methods, output_mode=output_mode)
        return jsonify({
            'success': True,
            'message': 'تبدیل به توزیع نرمال با موفقیت انجام شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در تبدیل به توزیع نرمال: {str(e)}'}), 500


@app.route('/process_plots', methods=['POST'])
def process_plots_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        interpolation = data.get('interpolation', 'idw')
        cmap = data.get('cmap', 'viridis')
        elements = data.get('elements')
        try:
            idw_k = int(data.get('idw_k', 12))
        except (TypeError, ValueError):
            idw_k = 12
        idw_k = max(1, min(idw_k, 50))

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        kriging_method = data.get('kriging_method', 'ordinary')
        if kriging_method not in ('ordinary', 'universal'):
            kriging_method = 'ordinary'
        kriging_variogram = data.get('kriging_variogram', 'spherical')
        if kriging_variogram not in ('spherical', 'exponential', 'gaussian', 'linear'):
            kriging_variogram = 'spherical'

        result = process_plots(
            session_id, source=source, interpolation=interpolation,
            cmap=cmap, elements=elements, idw_k=idw_k,
            kriging_method=kriging_method, kriging_variogram=kriging_variogram,
        )
        return jsonify({
            'success': True,
            'message': f'{result["count"]} نمودار با موفقیت ایجاد شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در رسم نمودارها: {str(e)}'}), 500


@app.route('/process_duplicates', methods=['POST'])
def process_duplicates_route():
    """تحلیل داده‌های تکراری (Duplicate QC) — شیت‌های Duplicate یا زوج‌های هم‌جوار."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        source = data.get('source', 'original')
        if source not in ('original', 'auto'):
            source = 'original'
        sheet_name = data.get('sheet_name')
        elements = data.get('elements') or None
        try:
            max_elements = int(data.get('max_elements', 20))
        except (TypeError, ValueError):
            max_elements = 20
        max_elements = max(1, min(max_elements, 100))
        left_coe = data.get('left_coe')
        right_coe = data.get('right_coe')

        result = process_duplicate_qc(
            session_id, sheet_name=sheet_name, source=source,
            elements=elements, left_coe=left_coe, right_coe=right_coe,
            max_elements=max_elements,
        )
        quality_counts = {}
        for s in result.get('stats', []):
            cat = s.get('Quality_Category', 'ضعیف')
            quality_counts[cat] = quality_counts.get(cat, 0) + 1

        return jsonify({
            'success': True,
            'message': f"تحلیل {result['n_pairs_total']} زوج تکراری برای {len(result['elements'])} عنصر انجام شد",
            'session_id': session_id,
            'quality_counts': quality_counts,
            **result,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'خطا در تحلیل داده‌های تکراری: {str(e)}'}), 500


@app.route('/duplicate_sheets', methods=['POST'])
def duplicate_sheets_route():
    """بررسی وجود شیت‌های Duplicate در فایل آپلودی و بازگرداندن عناصر آن‌ها."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        import pandas as pd
        filepath = get_session_upload_path(session_id)
        if not os.path.exists(filepath):
            return jsonify({'error': 'فایل آپلودی یافت نشد'}), 404

        excel = pd.ExcelFile(filepath)
        available = excel.sheet_names
        ds_sheet = next((s for s in ('Duplicate Samples', 'Duplicate_Samples', 'DuplicateSamples') if s in available), None)
        dd_sheet = next((s for s in ('Duplicate_Data', 'Duplicate Data', 'DuplicateData') if s in available), None)
        elements = []
        n_pairs = 0
        if ds_sheet and dd_sheet:
            dd_df = pd.read_excel(filepath, sheet_name=dd_sheet, nrows=50)
            elements = [c for c in dd_df.columns if c != 'Sample_ID']
            ds_df = pd.read_excel(filepath, sheet_name=ds_sheet)
            n_pairs = len(ds_df)

        return jsonify({
            'success': True,
            'has_duplicate_sheets': bool(ds_sheet and dd_sheet),
            'samples_sheet': ds_sheet,
            'data_sheet': dd_sheet,
            'elements': elements,
            'n_pairs': n_pairs,
            'available_sheets': available,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در بررسی شیت‌های تکراری: {str(e)}'}), 500


SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_\-]+$')


def _valid_session_id(session_id):
    """فقط شناسه‌های مجاز (بدون / و ..) پذیرفته می‌شوند."""
    return bool(SESSION_ID_RE.match(session_id or ''))


def _inside(base_dir, target_path):
    """بررسی اینکه target_path بعد از resolve شدن داخل base_dir باشد (محافظت path traversal)."""
    try:
        base = os.path.realpath(base_dir)
        target = os.path.realpath(target_path)
        return os.path.commonpath([base, target]) == base
    except ValueError:
        return False


@app.route('/download/<session_id>/<path:filename>')
def download_session_file(session_id, filename):
    try:
        if not _valid_session_id(session_id):
            return jsonify({'error': 'دسترسی غیرمجاز'}), 403
        session_dir = get_session_dir(session_id)
        file_path = os.path.join(session_dir, filename)
        if not _inside(session_dir, file_path):
            return jsonify({'error': 'دسترسی غیرمجاز'}), 403
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return jsonify({'error': 'فایل یافت نشد'}), 404
        mimetype = (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            if filename.lower().endswith('.xlsx')
            else None
        )
        return send_file(file_path, as_attachment=True, mimetype=mimetype)
    except Exception as e:
        return jsonify({'error': f'خطا در دانلود فایل: {str(e)}'}), 500


@app.route('/download/<path:filename>')
def download_file_legacy(filename):
    """سازگاری با مسیرهای قدیمی."""
    # فقط نام فایل ساده مجاز است (نه مسیر با / یا ..)
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        return jsonify({'error': 'دسترسی غیرمجاز'}), 403
    for base in ('output', 'sessions'):
        if not os.path.isdir(base):
            continue
        base_real = os.path.realpath(base)
        for root, _, files in os.walk(base_real):
            if safe_name in files:
                file_path = os.path.join(root, safe_name)
                if _inside(base_real, file_path):
                    return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'فایل یافت نشد'}), 404


@app.route('/download_all/<session_id>')
def download_all_session_files(session_id):
    try:
        if not _valid_session_id(session_id):
            return jsonify({'error': 'دسترسی غیرمجاز'}), 403
        session_path = get_session_dir(session_id)
        if not os.path.exists(session_path):
            return jsonify({'error': 'جلسه یافت نشد'}), 404

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, session_path)
                    zf.write(file_path, arcname)

        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'geochemistry_{session_id}.zip',
        )
    except Exception as e:
        return jsonify({'error': f'خطا در ایجاد فایل ZIP: {str(e)}'}), 500


@app.route('/sample_file')
def sample_file():
    try:
        return send_file(
            'static/files/sample_input.xlsx',
            as_attachment=True,
            download_name='نمونه_فایل_ورودی.xlsx',
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================================================
# Multifactor Analysis Endpoints
# ==================================================

@app.route('/process_correlation', methods=['POST'])
def process_correlation_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        method = data.get('method', 'pearson')
        source = data.get('source', 'auto')
        pvalue_filter = float(data.get('pvalue_filter', 0.05)) if data.get('pvalue_filter') else None
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_correlation_matrix(session_id, method=method, source=source, pvalue_filter=pvalue_filter)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در ماتریس همبستگی: {str(e)}'}), 500


@app.route('/process_pca', methods=['POST'])
def process_pca_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        n_components = int(data.get('n_components')) if data.get('n_components') else None
        standardize = data.get('standardize', True)
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_pca(session_id, source=source, n_components=n_components, standardize=standardize)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در PCA: {str(e)}'}), 500


@app.route('/process_hierarchical_clustering', methods=['POST'])
def process_hierarchical_clustering_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        n_clusters = int(data.get('n_clusters', 3))
        linkage_method = data.get('linkage_method', 'ward')
        distance_metric = data.get('distance_metric', 'euclidean')
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_hierarchical_clustering(session_id, source=source, n_clusters=n_clusters,
                                                  linkage_method=linkage_method, distance_metric=distance_metric)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در خوشه‌بندی سلسله‌مراتبی: {str(e)}'}), 500


@app.route('/process_kmeans', methods=['POST'])
def process_kmeans_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        n_clusters = int(data.get('n_clusters', 3))
        max_iter = int(data.get('max_iter', 300))
        n_init = int(data.get('n_init', 10))
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_kmeans(session_id, source=source, n_clusters=n_clusters, max_iter=max_iter, n_init=n_init)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در K-Means: {str(e)}'}), 500


@app.route('/process_factor_analysis', methods=['POST'])
def process_factor_analysis_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        rotation = data.get('rotation', 'varimax')
        n_factors = int(data.get('n_factors')) if data.get('n_factors') else None
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_factor_analysis(session_id, source=source, n_factors=n_factors, rotation=rotation)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در تحلیل فاکتوری: {str(e)}'}), 500


@app.route('/process_element_association', methods=['POST'])
def process_element_association_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        method = data.get('method', 'pearson')
        min_corr = float(data.get('min_corr', 0.5))
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_element_association(session_id, source=source, method=method, min_corr=min_corr)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در گروه‌بندی عناصر: {str(e)}'}), 500


@app.route('/process_mahalanobis', methods=['POST'])
def process_mahalanobis_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        confidence = float(data.get('confidence', 0.975))
        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400
        result = process_mahalanobis(session_id, source=source, confidence=confidence)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'خطا در محاسبه فاصله ماهالانوبی: {str(e)}'}), 500


# ==================================================
# پاک‌سازی خودکار جلسات/آپلودهای قدیمی (باگ ۴)
# ==================================================
SESSION_TTL_DAYS = config.SESSION_TTL_DAYS
_CLEANUP_STARTED = False


def cleanup_old_data(ttl_days=None):
    """حذف موارد قدیمی‌تر از TTL در پوشه‌های sessions/ و uploads/."""
    ttl = (SESSION_TTL_DAYS if ttl_days is None else ttl_days) * 86400
    cutoff = time.time() - ttl
    removed = 0
    for base in ('sessions', 'uploads'):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            path = os.path.join(base, name)
            try:
                if os.path.getmtime(path) <= cutoff:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                    removed += 1
            except OSError:
                continue
    return removed


def start_cleanup_scheduler(interval_hours=None):
    """راه‌اندازی thread پس‌زمینه برای پاک‌سازی دوره‌ای (یکبار)."""
    global _CLEANUP_STARTED
    if _CLEANUP_STARTED:
        return
    _CLEANUP_STARTED = True
    if interval_hours is None:
        interval_hours = config.CLEANUP_INTERVAL_HOURS

    def _loop():
        while True:
            try:
                cleanup_old_data()
            except Exception:
                pass
            time.sleep(interval_hours * 3600)

    threading.Thread(target=_loop, daemon=True).start()


if __name__ == '__main__':
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(config.SESSIONS_FOLDER, exist_ok=True)
    start_cleanup_scheduler()
    app.run(debug=config.DEBUG, host=config.HOST, port=config.PORT)

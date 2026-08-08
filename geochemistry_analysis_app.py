from flask import Flask, render_template, request, send_file, jsonify
import os
import uuid
import zipfile
import io
from datetime import datetime
from werkzeug.utils import secure_filename

from processing_services import (
    get_session_dir,
    get_session_upload_path,
    load_session_state,
    save_session_state,
    process_censored_data,
    process_outliers,
    process_normalization,
    process_plots,
)

app = Flask(__name__)
app.secret_key = 'geochemistry_analysis_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


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

        state = {
            'session_id': session_id,
            'original_filename': original_name,
            'sheet_name': default_sheet,
            'steps': {},
        }
        save_session_state(session_id, state)

        return jsonify({
            'success': True,
            'session_id': session_id,
            'filename': original_name,
            'sheet_names': sheet_names,
            'default_sheet': default_sheet,
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

        left_coe = float(data.get('left_coe', 0.75))
        right_coe = float(data.get('right_coe', 1.25))
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
            'message': 'پردازش داده‌های سانسور شده با موفقیت انجام شد',
            'session_id': session_id,
            **result,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'خطا در پردازش داده‌های سانسور شده: {str(e)}'}), 500


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


@app.route('/process_normalization', methods=['POST'])
def process_normalization_route():
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')
        methods = data.get('methods')

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_normalization(session_id, source=source, methods=methods)
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

        if not session_id:
            return jsonify({'error': 'شناسه جلسه الزامی است'}), 400

        result = process_plots(
            session_id, source=source, interpolation=interpolation,
            cmap=cmap, elements=elements,
        )
        return jsonify({
            'success': True,
            'message': f'{result["count"]} نمودار با موفقیت ایجاد شد',
            'session_id': session_id,
            **result,
        })
    except Exception as e:
        return jsonify({'error': f'خطا در رسم نمودارها: {str(e)}'}), 500


@app.route('/download/<session_id>/<path:filename>')
def download_session_file(session_id, filename):
    try:
        file_path = os.path.join(get_session_dir(session_id), filename)
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
    for root, _, files in os.walk('output'):
        if filename in files:
            return send_file(os.path.join(root, filename), as_attachment=True)
    for root, _, files in os.walk('sessions'):
        if filename in files:
            return send_file(os.path.join(root, filename), as_attachment=True)
    return jsonify({'error': 'فایل یافت نشد'}), 404


@app.route('/download_all/<session_id>')
def download_all_session_files(session_id):
    try:
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


if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    os.makedirs('sessions', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)

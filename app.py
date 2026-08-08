from flask import Flask, render_template, request, send_file, jsonify
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import subprocess
import json
import sys

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('dashboard/index.html')

@app.route('/sample_file')
def sample_file():
    try:
        return send_file('static/files/sample_input.xlsx',
                        as_attachment=True,
                        download_name='نمونه_فایل_ورودی.xlsx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/guide')
def guide():
    return render_template('dashboard/guide.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Create output directory for this run
            output_dir = os.path.join('output', timestamp)
            os.makedirs(output_dir, exist_ok=True)
            
            # Set environment variables for proper encoding
            my_env = os.environ.copy()
            my_env['PYTHONIOENCODING'] = 'utf-8'
            
            # Run read_duplicates.py with the uploaded file
            result = subprocess.run(
                ['python', 'read_duplicate_parallel.py', '--input', filepath, '--output', output_dir],              
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=my_env
            )
            
            if result.returncode != 0:
                return jsonify({'error': f'Error processing file: {result.stderr}'}), 500
            
            # Read the results from the output directory
            try:
                with open(os.path.join(output_dir, 'results.json'), 'r', encoding='utf-8') as f:
                    results = json.load(f)
            except Exception as e:
                return jsonify({'error': f'Error reading results: {str(e)}'}), 500
            
            # Count elements in each quality category
            quality_counts = {'خوب': 0, 'قابل قبول': 0, 'ضعیف': 0}
            for stat in results['stats']:
                quality_counts[stat['Quality_Category']] += 1
            
            # Prepare response data
            response_data = {
                'success': True,
                'message': 'تحلیل با موفقیت انجام شد',
                'results_dir': timestamp,
                'quality_summary': quality_counts,
                'top_elements': results['top_elements'][:5]  # Get top 5 elements
            }
            
            return jsonify(response_data)
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            # Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/results/<path:filename>')
def serve_result(filename):
    try:
        file_path = os.path.join('output', filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        app.logger.error(f"Error serving file {filename}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download_plots/<path:results_dir>')
def download_plots(results_dir):
    try:
        results_path = os.path.join('output', results_dir)
        if not os.path.exists(results_path):
            return jsonify({'error': 'Results directory not found'}), 404
            
        # Create a ZIP file containing all plots
        import zipfile
        import io
        
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add plots from all plot directories
            plot_dirs = ['scatter_plots', 'comparison_plots', 'log_thompson_howarth_plots']
            for plot_dir in plot_dirs:
                dir_path = os.path.join(results_path, plot_dir)
                if os.path.exists(dir_path):
                    for root, dirs, files in os.walk(dir_path):
                        for file in files:
                            if file.endswith('.png'):
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(plot_dir, file)
                                zf.write(file_path, arcname)
            
            # Add summary plots from the main output directory
            for file in ['mean_rpd_by_element.png', 'rpd_distribution.png']:
                file_path = os.path.join(results_path, file)
                if os.path.exists(file_path):
                    zf.write(file_path, file)
        
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'plots_{results_dir}.zip'
        )
    except Exception as e:
        app.logger.error(f"Error creating zip file for {results_dir}: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create necessary directories if they don't exist
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    app.run(debug=True) 
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QFileDialog, QMessageBox, 
                           QTabWidget, QScrollArea, QHBoxLayout, QProgressBar)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import subprocess
import json
from datetime import datetime
import shutil
import zipfile

class ProcessingThread(QThread):
    finished = pyqtSignal(dict, str)
    error = pyqtSignal(str)
    
    def __init__(self, input_file, output_dir):
        super().__init__()
        self.input_file = input_file
        self.output_dir = output_dir
        
    def run(self):
        try:
            # Run read_duplicates.py
            result = subprocess.run(
                ['python', 'read_duplicates.py', '--input', self.input_file, '--output', self.output_dir],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                raise Exception(f"Error processing file: {result.stderr}")
                
            # Read results
            with open(os.path.join(self.output_dir, 'results.json'), 'r', encoding='utf-8') as f:
                results = json.load(f)
                
            self.finished.emit(results, self.output_dir)
            
        except Exception as e:
            self.error.emit(str(e))

class GeochemistryAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Geochemistry Analyzer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Add tabs
        self.tabs.addTab(self.create_upload_tab(), "Upload Data")
        self.tabs.addTab(self.create_results_tab(), "Results")
        self.tabs.addTab(self.create_guide_tab(), "Guide")
        
        # Initialize variables
        self.current_file = None
        self.results_dir = None
        self.processing = False
        
    def create_upload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Upload section
        upload_layout = QHBoxLayout()
        self.upload_btn = QPushButton("Upload Excel File")
        self.upload_btn.setMinimumWidth(200)  # Set minimum width for all buttons
        self.upload_btn.clicked.connect(self.upload_file)
        upload_layout.addWidget(self.upload_btn)
        
        self.file_label = QLabel("No file selected")
        upload_layout.addWidget(self.file_label)
        
        layout.addLayout(upload_layout)
        
        # Process button
        self.process_btn = QPushButton("Process Data")
        self.process_btn.setMinimumWidth(200)
        self.process_btn.clicked.connect(self.process_data)
        self.process_btn.setEnabled(False)
        layout.addWidget(self.process_btn)
        
        # Progress bar and status
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        
        # Download buttons
        self.download_excel_btn = QPushButton("Download Excel Results")
        self.download_excel_btn.setMinimumWidth(200)
        self.download_excel_btn.clicked.connect(self.download_excel_results)
        self.download_excel_btn.setEnabled(False)
        layout.addWidget(self.download_excel_btn)
        
        self.download_all_btn = QPushButton("Download All Results (ZIP)")
        self.download_all_btn.setMinimumWidth(200)
        self.download_all_btn.clicked.connect(self.download_all_results)
        self.download_all_btn.setEnabled(False)
        layout.addWidget(self.download_all_btn)
        
        return tab
        
    def create_results_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create scroll area for results
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Add results widgets here
        self.results_label = QLabel("No results available")
        scroll_layout.addWidget(self.results_label)
        
        # Add download buttons
        self.download_plots_btn = QPushButton("Download Plots (ZIP)")
        self.download_plots_btn.setMinimumWidth(200)
        self.download_plots_btn.clicked.connect(self.download_plots)
        self.download_plots_btn.setEnabled(False)
        scroll_layout.addWidget(self.download_plots_btn)
        
        self.download_output_btn = QPushButton("Download Output Files (ZIP)")
        self.download_output_btn.setMinimumWidth(200)
        self.download_output_btn.clicked.connect(self.download_output_files)
        self.download_output_btn.setEnabled(False)
        scroll_layout.addWidget(self.download_output_btn)
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        return tab
        
    def create_guide_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Add guide content
        guide_text = """
        <div dir="rtl" style="text-align: right;">
        <h2>راهنمای استفاده از نرم‌افزار</h2>
        <p>فایل نمونه را از دکمه پایین صفحه می‌توانید دانلود کنید.</p>
        
        <h3>ساختار فایل ورودی</h3>
        <p>فایل ورودی باید یک فایل اکسل با دو شیت زیر باشد:</p>
        <ul style="text-align: right;">
            <li>
                <strong>Duplicate Samples</strong>
                <ul>
                    <li>شامل دو ستون:</li>
                    <li>Sample_ID: شناسه نمونه اصلی</li>
                    <li>Duplicated_Sample_ID: شناسه نمونه تکراری</li>
                </ul>
            </li>
            <li>
                <strong>Duplicate_Data</strong>
                <ul>
                    <li>شامل:</li>
                    <li>ستون Sample_ID: شناسه نمونه</li>
                    <li>ستون‌های عناصر: مقادیر آنالیز هر عنصر بصورت عددی</li>
                </ul>
            </li>
        </ul>

        <h3>نحوه استفاده</h3>
        <ol style="text-align: right;">
            <li>فایل اکسل ورودی را انتخاب کنید.</li>
            <li>دکمه Process را کلیک کنید.</li>
            <li>پس از آپلود، نرم‌افزار به طور خودکار تحلیل‌های زیر را انجام می‌دهد:
                <ul>
                    <li>محاسبه RPD برای هر عنصر</li>
                    <li>دسته‌بندی کیفیت عناصر</li>
                    <li>ایجاد نمودارهای تحلیلی</li>
                </ul>
            </li>
            <li>نتایج را می‌توانید به صورت:
                <ul>
                    <li>فایل اکسل حاوی آمار تفصیلی</li>
                    <li>مجموعه نمودارهای تحلیلی</li>
                </ul>
                دانلود کنید.
            </li>
        </ol>

        <h3>معیارهای دسته‌بندی کیفیت</h3>
        <ul style="text-align: right;">
            <li><strong>خوب:</strong> 90% نمونه‌ها دارای خطای کمتر از 10% و 99% نمونه‌ها دارای خطای کمتر از 20%</li>
            <li><strong>قابل قبول:</strong> 70% نمونه‌ها دارای خطای کمتر از 10% و 95% نمونه‌ها دارای خطای کمتر از 20%</li>
            <li><strong>ضعیف:</strong> خطای بیش از مقادیر ذکر شده در آیتم قبل</li>
        </ul>

        <div class="contributors" style="text-align: right;">
            <h4>تهیه‌کنندگان:</h4>
            <p>حسین فردوسی، حسن عزمی، حسن موسوی، مهدی آزادی</p>
        </div>
        </div>
        """
        guide_label = QLabel(guide_text)
        guide_label.setWordWrap(True)
        guide_label.setAlignment(Qt.AlignRight)
        guide_label.setLayoutDirection(Qt.RightToLeft)
        layout.addWidget(guide_label)
        
        # Add sample file download button
        self.sample_btn = QPushButton("Download Sample File")
        self.sample_btn.setMinimumWidth(200)
        self.sample_btn.clicked.connect(self.download_sample)
        layout.addWidget(self.sample_btn)
        
        return tab
        
    def upload_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_name:
            self.current_file = file_name
            self.file_label.setText(f"Selected: {os.path.basename(file_name)}")
            self.process_btn.setEnabled(True)
            
    def download_sample(self):
        try:
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save Sample File", "sample_input.xlsx", "Excel Files (*.xlsx)"
            )
            if file_name:
                # Copy sample file to selected location
                shutil.copy('static/files/sample_input.xlsx', file_name)
                QMessageBox.information(self, "Success", "Sample file downloaded successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download sample file: {str(e)}")
            
    def process_data(self):
        if not self.current_file:
            QMessageBox.warning(self, "Warning", "Please select a file first")
            return
            
        try:
            # Show progress bar and status before starting processing
            self.progress_bar.setVisible(True)
            self.status_label.setVisible(True)
            self.status_label.setText("درحال پردازش ... زمان تقریبی 2 دقیقه")
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.process_btn.setEnabled(False)
            self.upload_btn.setEnabled(False)
            
            # Create output directory
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.results_dir = os.path.join('output', timestamp)
            os.makedirs(self.results_dir, exist_ok=True)
            
            # Create and start processing thread
            self.processing_thread = ProcessingThread(self.current_file, self.results_dir)
            self.processing_thread.finished.connect(self.on_processing_finished)
            self.processing_thread.error.connect(self.on_processing_error)
            self.processing_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start processing: {str(e)}")
            self.reset_ui()
            
    def on_processing_finished(self, results, output_dir):
        try:
            # Update results tab
            self.update_results_tab(results, output_dir)
            
            # Enable download buttons
            self.download_plots_btn.setEnabled(True)
            self.download_output_btn.setEnabled(True)
            self.download_excel_btn.setEnabled(True)
            self.download_all_btn.setEnabled(True)
            
            QMessageBox.information(self, "Success", "Data processed successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update results: {str(e)}")
        finally:
            self.reset_ui()
            
    def on_processing_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Failed to process data: {error_message}")
        self.reset_ui()
        
    def reset_ui(self):
        # Hide progress bar and status
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.process_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
            
    def update_results_tab(self, results, output_dir):
        # Clear previous results
        self.results_label.clear()
        
        # Create new layout for results
        results_text = "<h2>نتایج تحلیل</h2>"
        
        # Add quality summary
        quality_counts = {'خوب': 0, 'قابل قبول': 0, 'ضعیف': 0}
        for stat in results['stats']:
            quality_counts[stat['Quality_Category']] += 1
            
        results_text += "<h3>خلاصه کیفیت</h3>"
        results_text += f"<p>خوب: {quality_counts['خوب']}</p>"
        results_text += f"<p>قابل قبول: {quality_counts['قابل قبول']}</p>"
        results_text += f"<p>ضعیف: {quality_counts['ضعیف']}</p>"
        
        # Add categorized elements
        results_text += "<h3>عناصر دسته‌بندی شده</h3>"
        
        # Group elements by quality
        elements_by_quality = {'خوب': [], 'قابل قبول': [], 'ضعیف': []}
        for stat in results['stats']:
            elements_by_quality[stat['Quality_Category']].append(stat['Element'])
            
        # Display elements for each quality category
        for quality, elements in elements_by_quality.items():
            if elements:
                results_text += f"<h4>{quality}:</h4>"
                # Split elements into lines of 5 elements each
                for i in range(0, len(elements), 5):
                    line_elements = elements[i:i+5]
                    results_text += f"<p>{', '.join(line_elements)}</p>"
        
        self.results_label.setText(results_text)
        self.results_label.setWordWrap(True)
        self.results_label.setAlignment(Qt.AlignRight)
        self.results_label.setLayoutDirection(Qt.RightToLeft)
        
    def download_plots(self):
        if not self.results_dir:
            QMessageBox.warning(self, "Warning", "No results available to download")
            return
            
        try:
            # Create ZIP file name
            zip_filename = f"plots_{os.path.basename(self.results_dir)}.zip"
            zip_path = os.path.join(self.results_dir, zip_filename)
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all plot files
                for root, dirs, files in os.walk(self.results_dir):
                    for file in files:
                        if file.endswith(('.png', '.jpg', '.jpeg')):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, self.results_dir)
                            zipf.write(file_path, arcname)
            
            # Ask user where to save the ZIP file
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Plots ZIP", zip_filename, "ZIP Files (*.zip)"
            )
            
            if save_path:
                # Copy ZIP file to selected location
                shutil.copy(zip_path, save_path)
                QMessageBox.information(self, "Success", "Plots downloaded successfully")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download plots: {str(e)}")
            
    def download_output_files(self):
        if not self.results_dir:
            QMessageBox.warning(self, "Warning", "No results available to download")
            return
            
        try:
            # Create ZIP file name
            zip_filename = f"output_{os.path.basename(self.results_dir)}.zip"
            zip_path = os.path.join(self.results_dir, zip_filename)
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files except plots
                for root, dirs, files in os.walk(self.results_dir):
                    for file in files:
                        if not file.endswith(('.png', '.jpg', '.jpeg', '.zip')):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, self.results_dir)
                            zipf.write(file_path, arcname)
            
            # Ask user where to save the ZIP file
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Output Files ZIP", zip_filename, "ZIP Files (*.zip)"
            )
            
            if save_path:
                # Copy ZIP file to selected location
                shutil.copy(zip_path, save_path)
                QMessageBox.information(self, "Success", "Output files downloaded successfully")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download output files: {str(e)}")
            
    def download_excel_results(self):
        if not self.results_dir:
            QMessageBox.warning(self, "Warning", "No results available to download")
            return
            
        try:
            # Find Excel file in results directory
            excel_files = [f for f in os.listdir(self.results_dir) if f.endswith(('.xlsx', '.xls'))]
            if not excel_files:
                QMessageBox.warning(self, "Warning", "No Excel results file found")
                return
                
            excel_file = excel_files[0]  # Get the first Excel file found
            excel_path = os.path.join(self.results_dir, excel_file)
            
            # Ask user where to save the Excel file
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Excel Results", excel_file, "Excel Files (*.xlsx)"
            )
            
            if save_path:
                # Copy Excel file to selected location
                shutil.copy(excel_path, save_path)
                QMessageBox.information(self, "Success", "Excel results downloaded successfully")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download Excel results: {str(e)}")
            
    def download_all_results(self):
        if not self.results_dir:
            QMessageBox.warning(self, "Warning", "No results available to download")
            return
            
        try:
            # Create ZIP file name
            zip_filename = f"all_results_{os.path.basename(self.results_dir)}.zip"
            zip_path = os.path.join(self.results_dir, zip_filename)
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files
                for root, dirs, files in os.walk(self.results_dir):
                    for file in files:
                        if not file.endswith('.zip'):  # Don't include other ZIP files
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, self.results_dir)
                            zipf.write(file_path, arcname)
            
            # Ask user where to save the ZIP file
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save All Results ZIP", zip_filename, "ZIP Files (*.zip)"
            )
            
            if save_path:
                # Copy ZIP file to selected location
                shutil.copy(zip_path, save_path)
                QMessageBox.information(self, "Success", "All results downloaded successfully")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download all results: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = GeochemistryAnalyzer()
    window.show()
    sys.exit(app.exec_()) 
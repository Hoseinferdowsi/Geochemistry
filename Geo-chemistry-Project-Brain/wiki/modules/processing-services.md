<div dir="rtl">

# ⚙️ هستهٔ پردازش — `processing_services.py`

به‌روزترین و منظم‌ترین ماژول پروژه؛ تمام منطق Pipeline ژئوشیمی این‌جا است.

## توابع اصلی

### مدیریت session
- `get_session_dir` / `get_session_upload_path` / `get_session_state_path`
- `load_session_state` / `save_session_state` — وضعیت مراحل در `pipeline_state.json`

### مرحلهٔ ۱ — سانسور
- `process_censored_data(session_id, sheet_name, left_coe, right_coe)`
- `_fix_censored_value` — تشخیص الگوی `<0.5` / `>100` با regex و اعمال ضریب
- `_process_censored_column` / `_count_cell_changes`
- خروجی: `01_censored_processed.xlsx`

### مرحلهٔ ۲ — Outliers
- `process_outliers(session_id, method, threshold, source)`
- روش‌ها: `iqr` / `zscore` / `dorfel` (از `outliers.py`)
- خروجی: `02_outliers_processed.xlsx`

### مرحلهٔ ۳ — نرمال‌سازی
- `process_normalization(session_id, source, methods)`
- تبدیل‌ها: Box-Cox ،Yeo-Johnson ،Quantile ،Rank-Based ،Log ،Sqrt
- ارزیابی با Shapiro-Wilk و انتخاب «بهترین روش» برای هر ستون
- خروجی: `03_normalized_data.xlsx` + `03_normalization_report.xlsx`

### مرحلهٔ ۴ — نمودارها
- `process_plots(session_id, source, interpolation, cmap, elements)`
- شناسایی خودکار ستون‌های مختصات (`_identify_coordinate_columns`)
- درون‌یابی IDW / Linear / Cubic / Nearest
- نقشهٔ توزیع هر عنصر + heatmap همبستگی
- خروجی: `04_plots/*.png`

### ابزارها
- `resolve_input_path` — انتخاب خودکار منبع ورودی هر مرحله
- `safe_to_excel` — ذخیرهٔ اتمی + پاک‌سازی کاراکترهای غیرمجاز Excel
- `_sanitize_for_excel` — حذف `inf` و کاراکترهای XML نامعتبر

## ثابت‌های مهم
- `EXCLUDED_COLUMNS` — ستون‌های شناسه/مختصات که پردازش نمی‌شوند
- `X_KEYWORDS` / `Y_KEYWORDS` — کلیدواژه‌های شناسایی مختصات
- `PIPELINE_STEPS` — نام فایل‌های خروجی هر مرحله

## نکات عملکردی
- ⚠️ `_idw_interpolation` حلقهٔ دوتایی O(grid²×n) دارد → پیشنهاد بهینه‌سازی (R9)
- ستون‌های مختصات با نام (نه dtype) شناسایی می‌شوند؛ اگر کلیدواژهٔ جدیدی در داده‌ها باشد باید به `X_KEYWORDS`/`Y_KEYWORDS` اضافه شود
</div>

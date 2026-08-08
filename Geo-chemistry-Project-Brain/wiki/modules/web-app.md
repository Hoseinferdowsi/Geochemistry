<div dir="rtl">

# 🌐 وباپ اصلی — `geochemistry_analysis_app.py`

وب‌اپلیکیشن Flask که Pipeline ژئوشیمی را به‌صورت **session-based** ارائه می‌دهد.

## Route ها

| Method | Route | عملکرد |
|---|---|---|
| GET | `/` | صفحهٔ اصلی (`geochemistry_analysis.html`) |
| POST | `/upload` | آپلود Excel، ایجاد session، خواندن شیت‌ها |
| GET | `/session/<id>/status` | وضعیت فعلی pipeline (برای refresh UI) |
| POST | `/process_censored_data` | مرحلهٔ ۱: پردازش سانسور |
| POST | `/process_outliers` | مرحلهٔ ۲: تشخیص Outlier |
| POST | `/process_normalization` | مرحلهٔ ۳: تبدیل به توزیع نرمال |
| POST | `/process_plots` | مرحلهٔ ۴: رسم نمودارها |
| GET | `/download/<session_id>/<path>` | دانلود یک فایل از session |
| GET | `/download_all/<session_id>` | دانلود همهٔ خروجی‌ها به‌صورت ZIP |
| GET | `/sample_file` | دانلود فایل نمونه |

## نکات مهم
- `session_id = YYYYMMDD_HHMMSS_xxxxxxx` (زمان + uuid کوتاه)
- `MAX_CONTENT_LENGTH = 32MB`، پسوند مجاز: `xlsx` / `xls`
- منطق پردازش در `processing_services.py` است؛ route ها فقط پارامتر را منتقل و نتیجهٔ JSON را برمی‌گردانند.
- `download_file_legacy` برای سازگاری با مسیرهای قدیمی وجود دارد.

## مسائل شناخته‌شده
- `secret_key` هاردکد شده (R10)
- مسیر دانلود بدون محصورسازی realpath — آسیب‌پذیری path traversal (B5)
- route های `process_*` پیام خطا را به‌صورت `str(e)` برمی‌گردانند که جزئیات داخلی را لو می‌دهد

## منابع
- هستهٔ پردازش → [[processing-services]]
- رابط کاربری → [[frontend]]
</div>

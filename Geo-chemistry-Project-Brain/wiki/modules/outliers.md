<div dir="rtl">

# 📊 تشخیص Outlier — `outliers.py`

ماژول تشخیص مقادیر خارج از رده؛ هم توسط وباپ (`processing_services.py`) و هم اسکریپت مستقل استفاده می‌شود.

## توابع

### `detect_outliers_iqr(data)`
- فاصلهٔ بین چارکی: `Q1 - 1.5×IQR` تا `Q3 + 1.5×IQR`
- مقادیر جایگزین = خودِ کران (winsorizing)
- مناسب داده‌های غیرنرمال

### `detect_outliers_zscore(data, threshold=3)`
- امتیاز استاندارد؛ مقادیر با |z| > آستانه → جایگزینی با کران میانگین ± آستانه×انحراف معیار
- مناسب داده‌های نرمال

### `detect_outliers_dorfel(data)`
- روش **بازگشتی** (تکراری): بزرگ‌ترین مقدار را حذف می‌کند، میانگین/انحراف معیار بقیه را حساب می‌کند و با ضریب g مقایسه می‌کند
- جدول `G_COEFFICIENTS` ضریب g را بر اساس تعداد نمونه با **درون‌یابی خطی** می‌دهد (`get_g_coefficient`)
- مقادیر خارج از آستانه با خودِ آستانه جایگزین می‌شوند
- ⚠️ پیچیدگی حلقهٔ while — برای داده‌های بزرگ کند است

## ورودی/خروجی
- ورودی: `pandas.Series`
- خروجی IQR/Z-Score: `(outliers_mask, replacement_values)`
- خروجی Dorfel: `Series` پردازش‌شده

## نکته
- `process_outliers(file_path, sheet_name, method, threshold)` (نسخهٔ CLI) هم در همین فایل است؛ وباپ از توابع `detect_*` مستقیماً استفاده می‌کند.
</div>

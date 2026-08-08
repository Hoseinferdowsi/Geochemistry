<div dir="rtl">

# 🎨 رابط کاربری — `templates/` و `static/`

## قالب‌های HTML

| فایل | وضعیت |
|---|---|
| `geochemistry_analysis.html` | ✅ **فعال** — قالب وباپ اصلی (RTL، Bootstrap 5) |
| `geochemistry_analysis_2.html` | ⚠️ تکراری |
| `geochemistry_analysis_edited.html` | ⚠️ تکراری |
| `index.html` | صفحهٔ ساده |
| `dashboard/` | قالب داشبورد نمونهٔ تکراری (از قالب دانلودشدهٔ Tooplate) |

## ویژگی‌های قالب اصلی (`geochemistry_analysis.html`)
- RTL + فونت IRANSansWeb
- ۶ تب با شمارهٔ مرحله: آپلود ← سانسور ← Outliers ← نرمال‌سازی ← نمودارها ← چندفاکتوری (Coming Soon)
- **نوار وضعیت pipeline** که مراحل انجام‌شده را سبز نشان می‌دهد
- آپلود با کشیدن-رها کردن + نوار پیشرفت
- انتخاب روش Outlier به‌صورت کارت‌های تعاملی + تنظیم آستانه Z-Score
- اعتبارسنجی ضرایب سانسور (هشدار برای مقادیر غیرمعمول)
- دانلود تکی هر خروجی + دکمهٔ «دانلود همهٔ خروجی‌ها (ZIP)»

## استاتیک
- `static/webfonts/` — Font Awesome
- `static/IRANSansWeb.woff` — فونت فارسی
- ⚠️ قالب به `/static/fonts/IRANSansWeb.woff` اشاره می‌کند ولی فایل در `static/IRANSansWeb.woff` است → **مسیر فونت خراب است** (در صورت بارگذاری، فونت fallback می‌شود)

## نکات
- قالب‌های تکراری (`_2` ،`_edited`) نباید ویرایش شوند؛ فقط `geochemistry_analysis.html` ملاک است (R1)
- افزودن تب «چندفاکتوری» و «آنومالی» → R7 ،R8
</div>

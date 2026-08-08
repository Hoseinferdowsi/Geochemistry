<div dir="rtl">

# 🏗️ معماری سیستم

## نمای کلی

پروژه از **دو سامانهٔ مجزا** تشکیل شده که داده‌های متفاوتی را تحلیل می‌کنند:

```
┌─────────────────────────────────────────────────────────────┐
│                   سامانهٔ ۱: Pipeline ژئوشیمی                 │
│                                                             │
│  geochemistry_analysis_app.py (Flask)                       │
│        │                                                    │
│        ▼                                                    │
│  processing_services.py ─── هستهٔ پردازش                     │
│        │                                                    │
│        ├──► outliers.py (IQR / Z-Score / Dorfel)            │
│        │                                                    │
│        ▼                                                    │
│  sessions/<session_id>/  (فایل‌های میانی + state)            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   سامانهٔ ۲: نمونه‌های تکراری                 │
│                                                             │
│  app.py (Flask) ──► read_duplicate_parallel.py (subprocess) │
│        │                    │                               │
│        │                    ▼                               │
│        │              output/<timestamp>/ (نتایج + plots)   │
│        └──► gui_app.py (PyQt5، همان منطق، رابط دسکتاپی)      │
└─────────────────────────────────────────────────────────────┘
```

## جریان داده در Pipeline ژئوشیمی

هر آپلود یک **session** با شناسهٔ `YYYYMMDD_HHMMSS_xxxxxxx` می‌گیرد:

```
آپلود Excel
   │  sessions/<session_id>/original.xlsx
   ▼
مرحله ۱: پردازش سانسور  →  01_censored_processed.xlsx
   ▼
مرحله ۲: Outliers        →  02_outliers_processed.xlsx
   ▼
مرحله ۳: نرمال‌سازی       →  03_normalized_data.xlsx + 03_normalization_report.xlsx
   ▼
مرحله ۴: نمودارها         →  04_plots/*.png (+ correlation_heatmap.png)
   ▼
دانلود (تکی یا ZIP همهٔ خروجی‌ها)
```

- **وضعیت هر مرحله** در `pipeline_state.json` داخل پوشهٔ session ذخیره می‌شود.
- هر مرحله می‌تواند «منبع ورودی» خودکار (آخرین مرحلهٔ انجام‌شده) یا صریح (original / censored / outliers / normalization) انتخاب کند — منطق در `resolve_input_path()`.
- خروجی Excel با **نوشتن اتمی** (فایل `.tmp` سپس جایگزینی) برای جلوگیری از فایل خراب ذخیره می‌شود.

## مسیرهای مهم

| مسیر | کاربرد |
|---|---|
| `sessions/<session_id>/` | همهٔ فایل‌های میانی و نتایج یک آپلود |
| `uploads/` | آپلودهای موقت (در session ها کپی می‌شوند) |
| `output/<timestamp>/` | خروجی سامانهٔ نمونه‌های تکراری |
| `templates/` | قالب‌های HTML |
| `static/` | فونت‌ها و فایل‌های استاتیک |

## نقاط ضعف معماری (خلاصه)
- دو سامانهٔ موازی با منطق تکراری؛ پیشنهاد ادغام → `roadmap.md` R1
- اسکریپت‌های مستقل تکراری → `roadmap.md` R2
- پاک‌سازی نشدن `sessions/` و `uploads/` → `bugs.md` B6
- جزئیات ماژول‌ها → [[modules/_index]]
</div>

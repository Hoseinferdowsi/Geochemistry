<div dir="rtl">

# 🧩 کاتالوگ ماژول‌ها

فهرست ماژول‌های پروژه به‌همراه نقش و وضعیت هر یک.

| ماژول | فایل(ها) | نقش | وضعیت |
|---|---|---|---|
| [[web-app]] | `geochemistry_analysis_app.py` | وباپ اصلی — route ها، session، دانلود | ✅ فعال |
| [[processing-services]] | `processing_services.py` | هستهٔ پردازش — کل pipeline | ✅ فعال (به‌روزترین) |
| [[outliers]] | `outliers.py` | الگوریتم‌های تشخیص Outlier | ✅ فعال |
| [[standalone-tools]] | `Anomaly_Detection.py` ،`Draw_Plot.py` ،`normalization_process.py` ،`convert_standard_scale.py` ،`Censored_Data.py` | اسکریپت‌های مستقل | ⚠️ تکراری/قدیمی |
| [[duplicates-analysis]] | `read_duplicate_parallel.py` ،`app.py` ،`gui_app.py` | تحلیل نمونه‌های تکراری | ⚠️ دو رابط موازی |
| [[frontend]] | `templates/` ،`static/` | رابط کاربری وب | ✅ فعال |

## ارتباط ماژول‌ها

```
وباپ اصلی (geochemistry_analysis_app.py)
        │
        ▼
processing_services.py ───► outliers.py
        │
        ▼
sessions/<session_id>/
```

> ⚠️ ماژول‌های مشخص‌شده با ⚠️ دارای نسخهٔ تکراری یا خرابی‌اند — جزئیات در `roadmap.md` (R1، R2) و `bugs.md`.
</div>

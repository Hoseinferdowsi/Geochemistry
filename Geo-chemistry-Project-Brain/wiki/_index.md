<div dir="rtl">

# 📚 ویکی پروژه — فهرست

دانشنامهٔ پروژهٔ تحلیل ژئوشیمی. هر بخش از این‌جا قابل دسترسی است.

## 🏠 بخش‌های اصلی

| بخش | توضیح |
|---|---|
| [[overview]] | نمای کلی پروژه، اهداف، تاریخچه |
| [[architecture]] | معماری سیستم و جریان داده |
| [[conventions]] | قواعد پروژه (لاگ، نام‌گذاری، سبک کد) |

## 🧩 ماژول‌ها

| ماژول | فایل(ها) | نقش |
|---|---|---|
| [[modules/web-app]] | `geochemistry_analysis_app.py` | وباپ اصلی — route ها و مدیریت session |
| [[modules/processing-services]] | `processing_services.py` | هستهٔ پردازش — کل pipeline |
| [[modules/outliers]] | `outliers.py` | روش‌های تشخیص مقادیر خارج از رده |
| [[modules/standalone-tools]] | `Anomaly_Detection.py` ،`Draw_Plot.py` ،`normalization_process.py` ،`convert_standard_scale.py` ،`Censored_Data.py` | اسکریپت‌های مستقل (بیشتر تکراری) |
| [[modules/duplicates-analysis]] | `read_duplicate_parallel.py` ،`app.py` ،`gui_app.py` | تحلیل نمونه‌های تکراری (RPD) |
| [[modules/frontend]] | `templates/` ،`static/` | رابط کاربری وب |

## 🔗 منابع بیرونی

- [`roadmap.md`](../roadmap.md) — طرح‌های در انتظار اجرا
- [`bugs.md`](../bugs.md) — باگ‌های شناخته‌شده
- [`ideas.md`](../ideas.md) — ایده‌ها
- [`logs.md`](../logs.md) — ثبت عملیات فنی
</div>

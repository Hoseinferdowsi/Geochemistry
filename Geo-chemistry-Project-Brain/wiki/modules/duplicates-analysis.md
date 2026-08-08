<div dir="rtl">

# 🔁 تحلیل نمونه‌های تکراری (Duplicate Samples)

سامانهٔ دوم پروژه برای **کنترل کیفیت آنالیز** — مقایسهٔ نمونه‌های تکراری و محاسبهٔ RPD.

## فایل‌ها

| فایل | نقش | وضعیت |
|---|---|---|
| `read_duplicate_parallel.py` | هستهٔ محاسبات: RPD، دسته‌بندی کیفیت، نمودارها | ✅ فعال |
| `app.py` | وباپ داشبورد (Flask) که اسکریپت را با subprocess صدا می‌زند | ⚠️ قدیمی‌تر |
| `gui_app.py` | رابط دسکتاپی PyQt5 با همین منطق | ❌ ارجاع خراب به `read_duplicates.py` (B1) |
| `read_duplicates_bkup.py` ،`_read_duplicates.py` | نسخه‌های قدیمی/پشتیبان | ⚠️ تکراری |
| `server.py` | اجرای `app.py` با Waitress روی پورت 80 | — |

## جریان کار (وباپ داشبورد)
```
آپلود Excel → read_duplicate_parallel.py --input → output/<timestamp>/
   ├── results.json (آمار + کیفیت هر عنصر)
   ├── scatter_plots/ , comparison_plots/ , log_thompson_howarth_plots/
   └── mean_rpd_by_element.png , rpd_distribution.png
```

## دسته‌بندی کیفیت
| دسته | معیار |
|---|---|
| خوب | 90% نمونه‌ها RPD<10% و 99% نمونه‌ها RPD<20% |
| قابل قبول | 70% نمونه‌ها RPD<10% و 95% نمونه‌ها RPD<20% |
| ضعیف | بقیه |

## ساختار فایل ورودی (طبق راهنمای gui_app)
- شیت `Duplicate Samples`: ستون‌های `Sample_ID` و `Duplicated_Sample_ID`
- شیت `Duplicate_Data`: ستون `Sample_ID` + ستون‌های عناصر

## مشکلات
- `gui_app.py` → `read_duplicates.py` ناموجود (B1) — باید به `read_duplicate_parallel.py` وصل شود (R3)
- منطق بین `app.py` و `gui_app.py` تکراری است → پیشنهاد یکپارچه‌سازی (R1)
</div>

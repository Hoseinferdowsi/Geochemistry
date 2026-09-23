# 📡 مستندات API — Geochemistry Analysis v3.1

پایه سرور: `http://localhost:5001`

تمام روت‌های `POST` بدنه JSON می‌پذیرند (`Content-Type: application/json`) و پاسخ نیز JSON است.
پارامتر مشترک `session_id` که با آپلود فایل صادر می‌شود.

**کدهای وضعیت:**
- `200` موفق | `400` ورودی نامعتبر | `403` دسترسی غیرمجاز | `404` یافت نشد | `500` خطای داخلی (پیام فارسی در `error`)

---

## مدیریت جلسه و فایل

### `POST /upload`
آپلود فایل اکسل و ساخت جلسه جدید.
- **ورودی:** `multipart/form-data` با فیلد `file` (xlsx/xls، حداکثر 32MB)
- **خروجی:** `session_id`, `filename`, `sheet_names`, `default_sheet`, `columns` (ستون‌های شیت پیش‌فرض)

### `GET /session/<session_id>/status`
وضعیت کامل جلسه (state ذخیره‌شده: مراحل انجام‌شده، ستون‌های X/Y انتخابی و …).

### `POST /get_columns`
ستون‌های یک شیت خاص را برگرداند.
- **ورودی:** `session_id`, `sheet_name`
- **خروجی:** `columns`

### `POST /save_coordinates`
ذخیره ستون‌های مختصات X/Y (از تحلیل‌ها مستثنی می‌شوند؛ `null` = خودکار).
- **ورودی:** `session_id`, `x_col`, `y_col`

### `GET /sample_file`
دانلود فایل نمونه ورودی.

---

## پایپ‌لاین پردازش

### `POST /process_censored_data`
تبدیل مقادیر سانسورشده `<x` و `>x`.
- **ورودی:** `session_id`, `sheet_name?`, `left_coe?` (پیش‌فرض 0.75), `right_coe?` (پیش‌فرض 1.25)

### `POST /process_outliers`
تشخیص مقادیر خارج از رده.
- **ورودی:** `session_id`, `method` (`iqr`|`zscore`|`dorfel`), `threshold?` (برای zscore، پیش‌فرض 3), `source?` (`auto`|`original`|`censored`|…)

### `POST /process_anomaly_separation`
جداسازی آنومالی با تعداد کلاس دلخواه (۲ تا ۱۰؛ کلاس ۰ = زمینه).
- **ورودی:**
  - `session_id`, `method` (`classical`|`boxplot`|`fractal`), `source?`
  - `num_classes?` (پیش‌فرض 3), `thresholds?` — لیست `n-1` آستانه/ضریب/درصد از خفیف تا شدید
  - سازگاری قدیمی: `light_threshold`, `strong_threshold`, `light_multiplier`, `strong_multiplier`, `light_percent`, `strong_percent`
- **خروجی:** `num_classes`, `class_totals`, `class_labels`, `anomaly_details` (تعداد و آستانه هر کلاس per ستون), `output_file`

### `POST /process_statistics`
آمار توصیفی ستون‌های عددی.
- **ورودی:** `session_id`, `source?`

### `POST /process_normalization`
تبدیل به توزیع نرمال.
- **ورودی:** `session_id`, `source?`
  - `methods?` — لیست روش‌ها: `Box-Cox`, `Yeo-Johnson`, `Quantile`, `Rank-Based`, `Log`, `Sqrt` (خالی = همه)
  - `output_mode?` — `best` (فقط بهترین روش هر ستون، پیش‌فرض) | `all` (همه روش‌های انتخابی)
- **خروجی:** نام ستون‌ها به فرم `عنصر_روش` + شیت‌های گزارش تفصیلی و خلاصه

### `POST /process_plots`
نقشه پراکندگی مکانی عناصر.
- **ورودی:** `session_id`, `source?`, `interpolation?` (`idw`|`kriging`|`linear`|`cubic`|`nearest`), `cmap?`
  - `elements?` — لیست نام ستون‌های موردنظر (خالی/نبود = همه عناصر)
  - `idw_k?` — تعداد همسایه‌های IDW (پیش‌فرض 12)
  - `kriging_method?` — `ordinary` (پیش‌فرض) | `universal`
  - `kriging_variogram?` — `spherical` (پیش‌فرض) | `exponential` | `gaussian` | `linear`
- **خروجی:** `count`, `generated_files`, `x_column`, `y_column`, `interpolation`
- **نکته:** کریجینگ به `pykrige` نیاز دارد (`pip install pykrige`) و سنگین‌تر از IDW است؛ گرید کوچک‌تر (۶۰×۶۰) و مقادیر بیرون از محدوده داده‌ها ماسک می‌شوند.

---

## تحلیل چندمتغیره

همه: `session_id`, `source?` به‌علاوه پارامترهای اختصاصی.
| روت | پارامترها | خروجی کلیدی |
|-----|-----------|-------------|
| `POST /process_correlation` | `method` (`pearson`\\|`spearman`\\|`kendall`), `pvalue_filter?` | `corr_matrix`, `corr_pairs`, `heatmap` |
| `POST /process_pca` | `n_components?`, `standardize?` | `eigenvalues`, `loadings`, `generated_plots` |
| `POST /process_hierarchical_clustering` | `n_clusters`, `linkage_method`, `distance_metric` | `cluster_stats`, `silhouette_score` |
| `POST /process_kmeans` | `n_clusters`, `max_iter?`, `n_init?` | `cluster_stats`, `inertia`, `elbow_data` |
| `POST /process_factor_analysis` | `n_factors?` (خالی = Kaiser), `rotation` (`varimax`\\|`promax`\\|`none`) | `loadings`, `variance`, `communalities`, `factor_names` |
| `POST /process_element_association` | `method`, `min_corr` (پیش‌فرض 0.5) | `pairs`, `group_details`, `generated_plots` |
| `POST /process_mahalanobis` | `confidence` (`0.95`\\|`0.975`\\|`0.99`) | `threshold`, `n_anomaly`, `top_rows` |

### `POST /duplicate_sheets`
بررسی وجود شیت‌های Duplicate در فایل آپلودی.
- **ورودی:** `session_id`
- **خروجی:** `has_duplicate_sheets`, `samples_sheet`, `data_sheet`, `elements`, `n_pairs`, `available_sheets`

### `POST /process_duplicates`
تحلیل داده‌های تکراری (Duplicate QC / Thompson-Howarth).
- **ورودی:** `session_id`, `source?` (`original` شیت‌های Duplicate | `auto` زوج‌های هم‌جوار ردیف فرد/زوج), `sheet_name?`, `elements?`, `max_elements?` (پیش‌فرض ۲۰), `left_coe?`, `right_coe?`
- **منبع original:** فایل باید شیت‌های «Duplicate Samples» (با Sample_ID و Duplicated_Sample_ID) و «Duplicate_Data» (با Sample_ID و عناصر) داشته باشد؛ مقادیر سنسورد `<x`/`>x` با ضرایب تعدیل پردازش می‌شوند.
- **خروجی:** `stats` (Mean/Median/Std RPD، درصد بالای ۱۰٪ و ۲۰٪، Quality_Category: خوب/قابل قبول/ضعیف)، `quality_counts`, `n_pairs_total`, `pair_source`
- **خروجی اکسل (۳ شیت):** خلاصه عناصر / جزئیات زوج‌ها / تنظیمات — نمودارها در `output/duplicates/` (pairs، Thompson-Howarth، comparison، RPD hist برای هر عنصر + summary_mean_rpd.png)

---

## دانلود

| روت | توضیح |
|-----|--------|
| `GET /download/<session_id>/<path:filename>` | دانلود یک فایل خروجی (محصور در پوشه جلسه — محافظت path traversal) |
| `GET /download/<filename>` | سازگاری با مسیرهای قدیمی (جست‌وجو در `output/` و `sessions/`) |
| `GET /download_all/<session_id>` | ZIP همه خروجی‌های جلسه |

---

## نمونه فراخوانی

```bash
curl -X POST http://localhost:5001/process_anomaly_separation \
  -H "Content-Type: application/json" \
  -d '{"session_id":"20260922_101500_ab12cd34","method":"classical","num_classes":5,"thresholds":[1.5,2,2.5,3]}'
```

## متغیرهای محیطی مؤثر بر API

| متغیر | پیش‌فرض | اثر |
|-------|---------|-----|
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `5001` | آدرس سرور |
| `FLASK_DEBUG` | `0` | حالت debug |
| `SECRET_KEY` | تصادفی | کلید session |
| `MAX_CONTENT_MB` | `32` | حداکثر حجم آپلود |
| `CENSOR_LEFT_COE` / `CENSOR_RIGHT_COE` | `0.75` / `1.25` | ضرایب پیش‌فرض سانسور |
| `SESSION_TTL_DAYS` | `7` | پاک‌سازی خودکار جلسات |
| `IDW_DEFAULT_K` | `12` | همسایه‌های پیش‌فرض IDW |

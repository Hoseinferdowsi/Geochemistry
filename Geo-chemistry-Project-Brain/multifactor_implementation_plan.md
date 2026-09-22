# 📊 برنامه اجرای تحلیل چندمتغیره (Multifactor Analysis)

## 📋 خلاصه وضعیت فعلی

- **تب چندفاکتوری:** فعلاً "Coming Soon" در وباپ
- **کتابخانه‌های موجود:** sklearn, scipy, numpy, pandas, matplotlib, seaborn
- **فایل plan اصلی:** شامل ۱۴ بخش (از Correlation Matrix تا Workflow)

---

## 🔍 بررسی و تصحیح plan.md

### ایرادات یافت‌شده:

1. **بخش ۱ موجود نیست:** plan از شماره ۲ شروع می‌شود — به نظر می‌رسد بخش ۱ (احتمالاً Data Preparation) در فایل دیگری یا حذف شده است.

2. **عدم تفکیک اولویت:** تمام ۱۴ بخش بدون اولویت‌بندی ارائه شده‌اند — برخی پیشرفته و برخی پایه‌ای هستند.

3. **وابستگی‌های کتابخانه‌ای ذکر نشده:** برخی روش‌ها نیاز به کتابخانه اضافی دارند:
   - **UMAP:** نیاز به `umap-learn`
   - **Compositional Data (CLR/ILR/ALR):** نیاز به `scikit-bio` یا پیاده‌سازی دستی
   - **Parallel Analysis:** پیاده‌سازی دستی یا استفاده از `-factor-analyzer`
   - **Gap Statistic:** پیاده‌سازی دستی

4. **ترتیب اجرایی مشخص نیست:** کدام بخش‌ها ابتدا و کدام بعداً باید پیاده‌سازی شوند.

5. **خروجی‌های فایل اکسل ذکر نشده:** مشخص نیست هر بخش چه خروجی‌ای باید داشته باشد.

---

## ✅ اصلاحات پیشنهادی برای plan.md

### اضافه کردن بخش ۱ (Data Preparation):
```
# 1. آماده‌سازی داده (Data Preparation)
- انتخاب ستون‌های عددی
- حذف مقادیر گمشده (Missing Data Handling)
- استانداردسازی (Standardization / Normalization)
- بررسی closure problem در داده‌های ژئوشیمیایی
```

### اضافه کردن اولویت‌بندی به هر بخش:
- **فاز ۱ (پایه‌ای):** Correlation, PCA, Cluster (اینها فوری‌ترین نیاز اکتشافی هستند)
- **فاز ۲ (میانی):** Factor Analysis, Element Association, Mahalanobis
- **فاز ۳ (پیشرفته):** Multivariate Anomaly, Compositional Data, Spatial Analysis
- **فاز ۴ (اختیاری):** Discriminant Analysis, Nonlinear, t-SNE/UMAP

### اضافه کردن نیازمندی‌های کتابخانه‌ای:
```
| بخش | کتابخانه مورد نیاز | وضعیت |
|------|-------------------|-------|
| Correlation | scipy, pandas | ✅ موجود |
| PCA | sklearn | ✅ موجود |
| Factor Analysis | sklearn | ✅ موجود |
| Cluster (Hierarchical) | scipy | ✅ موجود |
| Cluster (K-Means) | sklearn | ✅ موجود |
| Mahalanobis | scipy, numpy | ✅ موجود |
| Isolation Forest | sklearn | ✅ موجود |
| LOF | sklearn | ✅ موجود |
| t-SNE | sklearn | ✅ موجود |
| UMAP | umap-learn | ❌ نیاز به نصب |
| Compositional (CLR/ILR) | scikit-bio یا دستی | ⚠️ پیاده‌سازی دستی |
| Parallel Analysis | factor-analyzer یا دستی | ⚠️ پیاده‌سازی دستی |
| Gap Statistic | دستی | ⚠️ پیاده‌سازی دستی |
```

---

## 🚀 برنامه اجرایی پیشنهادی (فاز‌بندی)

### فاز ۱: تحلیل‌های پایه‌ای (اولویت بالا)
**هدف:** ارائه ابزارهای اصلی تحلیل چندمتغیره

| مرحله | تحلیل | خروجی‌ها | تقریب خطوط کد |
|--------|---------|----------|---------------|
| 1.1 | **ماتریس همبستگی** | Heatmap + جدول + p-values + فیلتر معناداری | ~200 |
| 1.2 | **PCA (تحلیل مؤلفه‌های اصلی)** | Eigenvalues, Scree Plot, Loadings, Scores, Biplot | ~400 |
| 1.3 | **Clustering سلسله‌مراتبی** | Dendrogram + خوشه‌بندی نمونه‌ها | ~250 |
| 1.4 | **K-Means** | Elbow Plot + Silhouette + خوشه‌بندی | ~200 |

**خروجی مشترک:** فایل اکسل چندشیته‌ای + نمودارها

### فاز ۲: تحلیل‌های میانی (اولویت متوسط)
**هدف:** تفسیر فرآیندهای ژئوشیمیایی

| مرحله | تحلیل | خروجی‌ها | تقریب خطوط کد |
|--------|---------|----------|---------------|
| 2.1 | **تحلیل فاکتوری** | Factor Loadings + Rotation + Communalities | ~300 |
| 2.2 | **گروه‌بندی عناصر** | Element Associations + Network Plot | ~250 |
| 2.3 | **فاصله Mahalanobis** | D² Score + Anomaly Detection | ~200 |

### فاز ۳: تحلیل‌های پیشرفته (اولویت کمتر)
**هدف:** تشخیص آنومالی چندمتغیره و تحلیل فضایی

| مرحله | تحلیل | خروجی‌ها | تقریب خطوط کد |
|--------|---------|----------|---------------|
| 3.1 | **آنومالی چندمتغیره** | Isolation Forest, LOF, Robust Mahalanobis | ~300 |
| 3.2 | **داده‌های ترکیبی (Compositional)** | CLR/ILR Transformation | ~250 |
| 3.3 | **تحلیل فضایی** | Moran's I, Hot Spot Analysis | ~300 |

### فاز ۴: تحلیل‌های اختیاری
**هدف:** ویژگی‌های پیشرفته برای کاربران حرفه‌ای

| مرحله | تحلیل | توضیح |
|--------|---------|--------|
| 4.1 | Discriminant Analysis | LDA/QDA (نیاز به برچسب کلاس) |
| 4.2 | تحلیل غیرخطی | Kernel PCA, Mutual Information |
| 4.3 | t-SNE / UMAP | Visualization پیشرفته |

---

## 📐 معماری پیشنهادی

### ساختار فایل‌ها:
```
processing_services.py (فعلی)
├── process_correlation_matrix()    # فاز ۱
├── process_pca()                   # فاز ۱
├── process_hierarchical_clustering() # فاز ۱
├── process_kmeans()                # فاز ۱
├── process_factor_analysis()       # فاز ۲
├── process_element_association()   # فاز ۲
├── process_mahalanobis()           # فاز ۲
├── process_multivariate_anomaly()  # فاز ۳
├── process_compositional()         # فاز ۳
└── process_spatial_analysis()      # فاز ۳
```

### ساختار تب HTML:
```html
<!-- Tab 8: Multifactor Analysis -->
<div class="tab-pane fade" id="tab-multifactor">
    <!-- Sub-tabs for different analyses -->
    <ul class="nav nav-pills mb-3">
        <li><button class="active" data-subtab="correlation">ماتریس همبستگی</button></li>
        <li><button data-subtab="pca">PCA</button></li>
        <li><button data-subtab="clustering">خوشه‌بندی</button></li>
        <li><button data-subtab="factor">تحلیل فاکتوری</button></li>
        <li><button data-subtab="multivariate-anomaly">آنومالی چندمتغیره</button></li>
    </ul>
    
    <!-- محتوای هر sub-tab -->
    <div class="tab-content">
        <!-- Correlation Tab -->
        <div id="subtab-correlation">...</div>
        <!-- PCA Tab -->
        <div id="subtab-pca">...</div>
        <!-- ... -->
    </div>
</div>
```

### ساختار خروجی اکسل:
```
multifactor_results.xlsx
├── ماتریس_همبستگی (Correlation Matrix)
├── p-values
├── PCA_Eigenvalues
├── PCA_Loadings
├── PCA_Scores
├── خوشه‌بندی_سلسله‌مراتبی
├── K-Means_Clusters
├── Factor_Loadings
├── Mahalanobis_Scores
└── آنومالی_چندمتغیره
```

---

## 📊 جدول زمانی پیشنهادی

| فاز | مدت تقریبی | وابستگی |
|-----|------------|---------|
| فاز ۱ (پایه‌ای) | ۳-۴ روز | ندارد |
| فاز ۲ (میانی) | ۲-۳ روز | فاز ۱ |
| فاز ۳ (پیشرفته) | ۳-۴ روز | فاز ۱ |
| فاز ۴ (اختیاری) | ۲-۳ روز | فاز ۱ |
| **جمع کل** | **۱۰-۱۴ روز** | - |

---

## ⚠️ نکات مهم اجرایی

### 1. استانداردسازی داده‌ها
- قبل از PCA، Factor Analysis، و Clustering حتماً داده‌ها باید **StandardScaler** شوند
- این کار قبلاً در `process_normalization` انجام می‌شود — باید از خروجی آن استفاده شود

### 2. مدیریت مقادیر گمشده
- قبل از تحلیل‌ها، مقادیر NaN باید مدیریت شوند
- گزینه‌ها: حذف ردیف، جایگزینی با میانگین/میانه، یا Imputation پیشرفته

### 3. انتخاب تعداد مؤلفه‌ها در PCA
- Kaiser Criterion (Eigenvalue > 1)
- Scree Test (نقطه آرنج)
- Parallel Analysis (مقایسه با داده‌های تصادفی)
- درصد واریانس تجمعی (مثلاً > 70%)

### 4. چرخش فاکتورها
- **Varimax:** چرخش orthogonal (عمودی) — تفسیر آسان‌تر
- **Promax/Oblimin:** چرخش oblique (مایل) — وقتی فاکتورها همبستگی دارند

### 5. خروجی نمودارها
- تمام نمودارها باید در پوشه `plots/` ذخیره شوند
- فرمت PNG با DPI=200
- نام‌گذاری فارسی و مناسب

### 6. جریان workflow پیشنهادی
```
داده خام → پردازش سنسورد → حذف Outlier → نرمال‌سازی
    ↓
انتخاب منبع داده (از مراحل قبل)
    ↓
انتخاب تحلیل مورد نظر
    ↓
پردازش و تولید نتایج
    ↓
ذخیره در فایل اکسل + نمودارها
```

---

## 🎯 معیارهای موفقیت

1. **عملکرد:** اجرا روی فایل‌های ۱۰۰۰+ ردیفی کمتر از ۳۰ ثانیه باشد
2. **دقت:** نتایج با نرم‌افزارهای مرجع (R, Python standalone) مقایسه شود
3. **-usability:** رابط کاربری ساده و بدون نیاز به دانش آماری پیشرفته
4. **خروجی:** فایل اکسل کامل با تمام توضیحات فارسی
5. **انعطاف‌پذیری:** امکان انتخاب منبع داده از مراحل مختلف pipeline

---

**تهیه‌کننده:** Buffy (Codebuff)  
**تاریخ:** ۲۰۲۶-۰۹-۱۳  
**وضعیت:** آماده اجرا

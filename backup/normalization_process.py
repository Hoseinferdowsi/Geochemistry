import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import scipy.stats as stats
from scipy.special import erfinv
from sklearn.preprocessing import QuantileTransformer, PowerTransformer
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# تنظیمات نمایش
pd.set_option('display.max_columns', None)

# ==================================================
# 1. خواندن فایل اکسل
# ==================================================
data_dir = Path('D:/03_AI/AI_Programming/Geochemistry_v3.0/Data')
file_path = data_dir / 'censored_processed_dorfel.xlsx'

print(f"در حال خواندن فایل: {file_path}")
df = pd.read_excel(file_path)
print(f"فایل خوانده شد: {df.shape[0]} ردیف و {df.shape[1]} ستون")

# ==================================================
# 2. شناسایی ستون‌ها
# ==================================================
excluded_columns = ['name', 'id', 'coordinates', 'Name', 'ID', 'Coordinates', 
                    'sample_name', 'sample_id', 'Sample', 'SampleID', 'Depth', 'depth']

# ستون‌های غیرعددی و مستثنی
excluded = [col for col in excluded_columns if col in df.columns]
numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
columns_to_transform = [col for col in numeric_columns if col not in excluded]

print(f"\nستون‌های عددی که تبدیل می‌شوند: {columns_to_transform}")
print(f"ستون‌های مستثنی: {excluded}")

if len(columns_to_transform) == 0:
    print("هیچ ستون عددی قابل تبدیلی یافت نشد!")
    exit()

# ==================================================
# 3. توابع تبدیل به توزیع نرمال
# ==================================================

def boxcox_transform(data):
    """تبدیل Box-Cox (فقط برای داده‌های مثبت)"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    
    # بررسی مثبت بودن داده‌ها
    if np.any(data_clean <= 0):
        # افزودن یک مقدار کوچک به داده‌ها
        min_val = np.min(data_clean)
        if min_val <= 0:
            shift = abs(min_val) + 0.001
            data_shifted = data_clean + shift
            print(f"  توجه: به داده‌های {shift:.3f} اضافه شد (منفی یا صفر وجود داشت)")
        else:
            data_shifted = data_clean
    else:
        data_shifted = data_clean
    
    try:
        transformed, lambda_val = stats.boxcox(data_shifted)
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result, lambda_val
    except:
        print(f"  خطا در Box-Cox تبدیل")
        return data, None

def yeojohnson_transform(data):
    """تبدیل Yeo-Johnson (برای داده‌های مثبت و منفی)"""
    pt = PowerTransformer(method='yeo-johnson')
    data_clean = data[~np.isnan(data)].reshape(-1, 1)
    if len(data_clean) < 3:
        return data
    
    try:
        transformed = pt.fit_transform(data_clean).flatten()
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result, pt.lambdas_[0]
    except:
        print(f"  خطا در Yeo-Johnson تبدیل")
        return data, None

def quantile_normalize(data):
    """تبدیل Quantile به توزیع نرمال"""
    qt = QuantileTransformer(output_distribution='normal', random_state=42)
    data_clean = data[~np.isnan(data)].reshape(-1, 1)
    if len(data_clean) < 3:
        return data
    
    try:
        transformed = qt.fit_transform(data_clean).flatten()
        result = np.full_like(data, np.nan)
        result[~np.isnan(data)] = transformed
        return result
    except:
        print(f"  خطا در Quantile تبدیل")
        return data

def rank_based_normalize(data):
    """تبدیل مبتنی بر رتبه (Rank-based inverse normal)"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    
    # محاسبه رتبه‌ها
    ranks = stats.rankdata(data_clean)
    # تبدیل رتبه به percentiles
    percentiles = (ranks - 0.5) / len(data_clean)
    # تبدیل به نمرات z (نرمال استاندارد)
    z_scores = stats.norm.ppf(percentiles)
    
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = z_scores
    return result

def log_transform(data):
    """تبدیل لگاریتمی (برای داده‌های چوله به راست)"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    
    # بررسی مقادیر مثبت
    if np.any(data_clean <= 0):
        min_val = np.min(data_clean)
        shift = abs(min_val) + 0.001
        data_shifted = data_clean + shift
    else:
        data_shifted = data_clean
    
    transformed = np.log(data_shifted)
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = transformed
    return result

def sqrt_transform(data):
    """تبدیل ریشه دوم"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return data
    
    # بررسی مقادیر منفی
    if np.any(data_clean < 0):
        min_val = np.min(data_clean)
        shift = abs(min_val) + 0.001
        data_shifted = data_clean + shift
    else:
        data_shifted = data_clean
    
    transformed = np.sqrt(data_shifted)
    result = np.full_like(data, np.nan)
    result[~np.isnan(data)] = transformed
    return result

# فرهنگ توابع تبدیل (برمی‌گردانند: transformed_data, additional_info)
transform_methods = {
    'Box-Cox': boxcox_transform,
    'Yeo-Johnson': yeojohnson_transform,
    'Quantile': quantile_normalize,
    'Rank-Based': rank_based_normalize,
    'Log': log_transform,
    'Sqrt': sqrt_transform
}

# ==================================================
# 4. توابع ارزیابی تطابق با توزیع نرمال
# ==================================================

def shapiro_wilk_test(data):
    """آزمون Shapiro-Wilk - p-value بالاتر = تطابق بهتر"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return np.nan, np.nan
    if len(data_clean) > 5000:
        # برای داده‌های بزرگ، نمونه‌گیری تصادفی
        data_clean = np.random.choice(data_clean, 5000, replace=False)
    try:
        statistic, p_value = stats.shapiro(data_clean)
        return statistic, p_value
    except:
        return np.nan, np.nan

def skewness(data):
    """چولگی - مقدار نزدیک به صفر = متقارن‌تر"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return np.nan
    return stats.skew(data_clean)

def kurtosis(data):
    """کورتوزیس - مقدار نزدیک به ۳ = دمای نرمال"""
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return np.nan
    return stats.kurtosis(data_clean, fisher=False)  # Fisher=False برای مقایسه با نرمال (=3)

def normality_score(data):
    """نمره ترکیبی تطابق با نرمال (p-value نرمال‌شده)"""
    _, p_value = shapiro_wilk_test(data)
    return p_value

# ==================================================
# 5. اعمال تبدیل‌ها بر روی هر ستون
# ==================================================

results = []

for col in columns_to_transform:
    print(f"\nپردازش ستون: {col}")
    original_data = df[col].values.copy()
    
    # معیارهای اولیه
    original_skew = skewness(original_data)
    original_kurt = kurtosis(original_data)
    original_pvalue = normality_score(original_data)
    original_std = np.nanstd(original_data)
    
    for method_name, method_func in transform_methods.items():
        try:
            # اعمال تبدیل
            result = method_func(original_data)
            
            # برای روش‌هایی که دو مقدار برمی‌گردانند
            if isinstance(result, tuple):
                transformed_data, param = result
                param_info = f"λ={param:.3f}" if param is not None else "N/A"
            else:
                transformed_data = result
                param_info = "N/A"
            
            # محاسبه معیارهای پس از تبدیل
            transformed_skew = skewness(transformed_data)
            transformed_kurt = kurtosis(transformed_data)
            transformed_pvalue = normality_score(transformed_data)
            transformed_std = np.nanstd(transformed_data)
            
            # محاسبه بهبودها
            skew_improvement = abs(original_skew) - abs(transformed_skew) if not np.isnan(original_skew) and not np.isnan(transformed_skew) else np.nan
            kurt_improvement = abs(original_kurt - 3) - abs(transformed_kurt - 3) if not np.isnan(original_kurt) and not np.isnan(transformed_kurt) else np.nan
            pvalue_improvement = transformed_pvalue - original_pvalue if not np.isnan(original_pvalue) and not np.isnan(transformed_pvalue) else np.nan
            
            results.append({
                'Column': col,
                'Method': method_name,
                'Parameter': param_info,
                'Original_Skewness': original_skew,
                'Transformed_Skewness': transformed_skew,
                'Skew_Improvement': skew_improvement,
                'Original_Kurtosis': original_kurt,
                'Transformed_Kurtosis': transformed_kurt,
                'Kurtosis_Improvement': kurt_improvement,
                'Original_Shapiro_pvalue': original_pvalue,
                'Transformed_Shapiro_pvalue': transformed_pvalue,
                'Shapiro_Improvement': pvalue_improvement,
                'Better_Fit': transformed_pvalue > original_pvalue if not np.isnan(transformed_pvalue) and not np.isnan(original_pvalue) else False
            })
            
            # ذخیره داده‌های تبدیل‌شده
            col_name_safe = f"{col}_transformed_{method_name.replace('-', '_').replace(' ', '_')}"
            df[col_name_safe] = transformed_data
            
            print(f"  ✓ {method_name}: p-value از {original_pvalue:.4f} → {transformed_pvalue:.4f} (بهبود: {pvalue_improvement:+.4f})")
            
        except Exception as e:
            print(f"  ✗ خطا در {method_name}: {str(e)[:50]}")
            results.append({
                'Column': col,
                'Method': method_name,
                'Parameter': 'Error',
                'Original_Skewness': original_skew,
                'Transformed_Skewness': np.nan,
                'Skew_Improvement': np.nan,
                'Original_Kurtosis': original_kurt,
                'Transformed_Kurtosis': np.nan,
                'Kurtosis_Improvement': np.nan,
                'Original_Shapiro_pvalue': original_pvalue,
                'Transformed_Shapiro_pvalue': np.nan,
                'Shapiro_Improvement': np.nan,
                'Better_Fit': False
            })

# ==================================================
# 6. نمایش نتایج
# ==================================================

results_df = pd.DataFrame(results)

print("\n" + "="*100)
print("نتایج ارزیابی تبدیل به توزیع نرمال")
print("="*100)
print("\nمعیارهای ارزیابی:")
print("- Shapiro-Wilk p-value: بالاتر = تطابق بهتر با منحنی نرمال (محدوده 0 تا 1)")
print("- Skewness (چولگی): نزدیک به صفر = متقارن‌تر ← 0.5~0.8 عالی")
print("- Kurtosis (کورتوزیس): نزدیک به 3 = دمای نرمال (3 = نرمال استاندارد)")
print("- Improvement: مثبت = بهبود")

# نمایش نتایج برای هر ستون و هر روش
for col in columns_to_transform:
    col_results = results_df[results_df['Column'] == col]
    print(f"\n{'='*80}")
    print(f"ستون: {col}")
    print(f"{'='*80}")
    
    # مرتب‌سازی بر اساس p-value پس از تبدیل
    col_results_sorted = col_results.sort_values('Transformed_Shapiro_pvalue', ascending=False)
    
    print(f"{'Method':<15} {'p-value(orig)':>12} {'p-value(trans)':>12} {'p-value Δ':>10} {'Skewness(orig)':>12} {'Skewness(trans)':>12} {'Better':>8}")
    print("-"*85)
    
    for _, row in col_results_sorted.iterrows():
        better_mark = "✓" if row['Better_Fit'] else "✗"
        print(f"{row['Method']:<15} {row['Original_Shapiro_pvalue']:>12.4f} {row['Transformed_Shapiro_pvalue']:>12.4f} "
              f"{row['Shapiro_Improvement']:>+10.4f} {row['Original_Skewness']:>12.4f} "
              f"{row['Transformed_Skewness']:>12.4f} {better_mark:>8}")
    
    # بهترین روش برای این ستون
    best_method = col_results.loc[col_results['Transformed_Shapiro_pvalue'].idxmax()]
    print(f"\n★ بهترین روش برای {col}: {best_method['Method']} (p-value = {best_method['Transformed_Shapiro_pvalue']:.4f})")

# ==================================================
# 7. ذخیره نتایج
# ==================================================

output_dir = data_dir / 'normalized_results'
output_dir.mkdir(exist_ok=True)

# ذخیره داده‌های اصلی + تبدیل‌شده
output_file = output_dir / f'transformed_{file_path.stem}.xlsx'
df.to_excel(output_file, index=False)
print(f"\nداده‌های تبدیل‌شده در فایل '{output_file}' ذخیره شدند.")

# ذخیره گزارش نتایج
report_file = output_dir / f'transformation_report_{file_path.stem}.xlsx'
results_df.to_excel(report_file, index=False)
print(f"گزارش تبدیل‌ها در فایل '{report_file}' ذخیره شد.")

# ==================================================
# 8. رسم نمودارهای مقایسه (برای 2 ستون اول)
# ==================================================

n_plot_cols = min(2, len(columns_to_transform))

for idx, col in enumerate(columns_to_transform[:n_plot_cols]):
    fig, axes = plt.subplots(2, len(transform_methods) + 1, figsize=(20, 10))
    fig.suptitle(f'تبدیل به توزیع نرمال - ستون: {col}', fontsize=16)
    
    # ردیف اول: هیستوگرام‌ها
    # ردیف دوم: QQ-plot‌ها
    
    # داده اصلی
    original_clean = df[col].dropna()
    
    # هیستوگرام اصلی
    axes[0, 0].hist(original_clean, bins=30, alpha=0.7, color='blue', edgecolor='black')
    axes[0, 0].set_title(f'Original Data\nSkew={skewness(original_clean):.3f}\np-value={normality_score(original_clean):.4f}')
    axes[0, 0].set_xlabel('Value')
    axes[0, 0].set_ylabel('Frequency')
    
    # QQ-plot اصلی
    stats.probplot(original_clean, dist="norm", plot=axes[1, 0])
    axes[1, 0].set_title(f'Original QQ-plot')
    
    # برای هر روش تبدیل
    for j, (method_name, method_func) in enumerate(transform_methods.items(), start=1):
        try:
            result = method_func(df[col].values)
            if isinstance(result, tuple):
                transformed_data = result[0]
            else:
                transformed_data = result
            
            transformed_clean = transformed_data[~np.isnan(transformed_data)]
            
            if len(transformed_clean) > 3:
                # هیستوگرام
                axes[0, j].hist(transformed_clean, bins=30, alpha=0.7, color='green', edgecolor='black')
                axes[0, j].set_title(f'{method_name}\nSkew={skewness(transformed_clean):.3f}\np-value={normality_score(transformed_clean):.4f}')
                axes[0, j].set_xlabel('Transformed Value')
                axes[0, j].set_ylabel('Frequency')
                
                # QQ-plot
                stats.probplot(transformed_clean, dist="norm", plot=axes[1, j])
                axes[1, j].set_title(f'{method_name} QQ-plot')
        except:
            axes[0, j].text(0.5, 0.5, f'{method_name}\nError', ha='center', va='center', transform=axes[0, j].transAxes)
            axes[1, j].text(0.5, 0.5, 'Error', ha='center', va='center', transform=axes[1, j].transAxes)
    
    plt.tight_layout()
    plt.savefig(output_dir / f'transformation_comparison_{col}.png', dpi=150, bbox_inches='tight')
    plt.show()

print("\n✓ پردازش با موفقیت به پایان رسید!")
print(f"✓ تمام نتایج در دایرکتوری '{output_dir}' ذخیره شدند.")
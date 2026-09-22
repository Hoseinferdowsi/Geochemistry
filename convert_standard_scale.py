import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import scipy.stats as stats
from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ==================================================
# 1. پیدا کردن و خواندن فایل اکسل
# ==================================================
import argparse

parser = argparse.ArgumentParser(description='Convert to Standard Scale')
parser.add_argument('--input', type=str, required=True, help='Path to input Excel file')
parser.add_argument('--output-dir', type=str, default=None, help='Output directory (default: input file parent / normalized_results)')
args = parser.parse_args()

file_path = Path(args.input)
data_dir = file_path.parent if args.output_dir is None else Path(args.output_dir)

# اگر فایل مستقیم پیدا نشد، به دنبال فایل‌های اکسل در دایرکتوری بگرد
if not file_path.exists():
    print(f"فایل {file_path} یافت نشد.")
    print(f"جستجو در دایرکتوری {data_dir}...")
    
    # پیدا کردن همه فایل‌های اکسل
    excel_files = list(data_dir.glob('*.xlsx')) + list(data_dir.glob('*.xls'))
    
    if not excel_files:
        print("هیچ فایل اکسیلی در دایرکتوری یافت نشد!")
        print("لطفاً مسیر صحیح را تنظیم کنید.")
        exit()
    
    print(f"\n{len(excel_files)} فایل اکسل یافت شد:")
    for i, f in enumerate(excel_files, 1):
        print(f"{i}. {f.name}")
    
    # اگر فقط یک فایل وجود دارد، از آن استفاده کن
    if len(excel_files) == 1:
        file_path = excel_files[0]
        print(f"\nاستفاده از فایل: {file_path.name}")
    else:
        # اگر چند فایل وجود دارد، از کاربر بخواه انتخاب کند
        try:
            choice = int(input("\nشماره فایل مورد نظر را وارد کنید: "))
            if 1 <= choice <= len(excel_files):
                file_path = excel_files[choice - 1]
                print(f"\nانتخاب شد: {file_path.name}")
            else:
                print("انتخاب نامعتبر!")
                exit()
        except ValueError:
            print("ورودی نامعتبر!")
            exit()

# خواندن فایل
print(f"\nدر حال خواندن فایل: {file_path}")
try:
    df = pd.read_excel(file_path)
    print(f"فایل با موفقیت خوانده شد. {df.shape[0]} ردیف و {df.shape[1]} ستون.")
except Exception as e:
    print(f"خطا در خواندن فایل: {e}")
    exit()

# ادامه کد اصلی (ادامه از بخش 2 کد قبلی)
print("\nستون‌های موجود در فایل:")
print(df.columns.tolist())
print("\n۵ ردیف اول:")
print(df.head())

# ==================================================
# 2. تشخیص ستون‌های غیرعددی و مستثنی‌شده
# ==================================================
excluded_columns = ['name', 'id', 'coordinates', 'Name', 'ID', 'Coordinates', 
                    'sample_name', 'sample_id', 'Sample', 'SampleID']
# پیدا کردن ستون‌هایی که در لیست مستثنی هستند
excluded = [col for col in excluded_columns if col in df.columns]
numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
# حذف ستون‌های مستثنی از لیست عددی
columns_to_normalize = [col for col in numeric_columns if col not in excluded]

print(f"\nستون‌های عددی که نرمال می‌شوند: {columns_to_normalize}")
print(f"ستون‌های مستثنی: {excluded}")

if len(columns_to_normalize) == 0:
    print("هیچ ستون عددی قابل نرمال‌سازی یافت نشد!")
    print("ستون‌های موجود:", df.columns.tolist())
    exit()

# ==================================================
# 3. توابع نرمال‌سازی (بقیه کد مثل قبل)
# ==================================================
def min_max_normalize(data):
    scaler = MinMaxScaler()
    # حذف NaNها برای نرمال‌سازی
    mask = ~np.isnan(data)
    if not np.any(mask):
        return data
    data_clean = data[mask]
    normalized_clean = scaler.fit_transform(data_clean.reshape(-1, 1)).flatten()
    result = np.full_like(data, np.nan)
    result[mask] = normalized_clean
    return result

def z_score_normalize(data):
    scaler = StandardScaler()
    mask = ~np.isnan(data)
    if not np.any(mask):
        return data
    data_clean = data[mask]
    normalized_clean = scaler.fit_transform(data_clean.reshape(-1, 1)).flatten()
    result = np.full_like(data, np.nan)
    result[mask] = normalized_clean
    return result

def robust_normalize(data):
    scaler = RobustScaler()
    mask = ~np.isnan(data)
    if not np.any(mask):
        return data
    data_clean = data[mask]
    normalized_clean = scaler.fit_transform(data_clean.reshape(-1, 1)).flatten()
    result = np.full_like(data, np.nan)
    result[mask] = normalized_clean
    return result

norm_methods = {
    'Min-Max': min_max_normalize,
    'Z-Score': z_score_normalize,
    'Robust': robust_normalize
}

# ==================================================
# 4. تابع محاسبه تطابق با توزیع نرمال
# ==================================================
def normality_score(data):
    data_clean = data[~np.isnan(data)]
    if len(data_clean) < 3:
        return np.nan
    try:
        stat, p_value = stats.shapiro(data_clean)
        return p_value
    except:
        return np.nan

# ==================================================
# 5. اعمال نرمال‌سازی و محاسبه تطابق
# ==================================================
results = []

for col in columns_to_normalize:
    original_data = df[col].values
    original_norm_score = normality_score(original_data)
    
    for method_name, method_func in norm_methods.items():
        transformed_data = method_func(original_data.copy())
        transformed_norm_score = normality_score(transformed_data)
        
        results.append({
            'Column': col,
            'Method': method_name,
            'Original_Normality_pvalue': original_norm_score,
            'Transformed_Normality_pvalue': transformed_norm_score,
            'Improvement': transformed_norm_score - original_norm_score if not np.isnan(transformed_norm_score) and not np.isnan(original_norm_score) else np.nan,
            'Better_Fit': transformed_norm_score > original_norm_score if not np.isnan(transformed_norm_score) and not np.isnan(original_norm_score) else False
        })
        
        # ذخیره داده‌های تبدیل‌شده
        col_name_safe = f"{col}_norm_{method_name.replace('-','_')}"
        df[col_name_safe] = transformed_data

# ==================================================
# 6. نمایش نتایج
# ==================================================
results_df = pd.DataFrame(results)
print("\n" + "="*80)
print("نتایج ارزیابی تطابق با توزیع نرمال (p-value Shapiro-Wilk)")
print("مقدار بالاتر = تطابق بیشتر با منحنی نرمال")
print("="*80)
print(results_df.to_string(index=False))

# ==================================================
# 7. ذخیره فایل خروجی
# ==================================================
output_dir = data_dir / 'normalized_results'
output_dir.mkdir(exist_ok=True)
output_file = output_dir / f'normalized_{file_path.stem}.xlsx'
df.to_excel(output_file, index=False)
print(f"\nداده‌های نرمال‌شده در فایل '{output_file}' ذخیره شدند.")

# ==================================================
# 8. رسم QQ-plot (اختیاری)
# ==================================================
if len(columns_to_normalize) > 0:
    sample_col = columns_to_normalize[0]
    print(f"\nرسم QQ-plot برای ستون '{sample_col}' ...")
    
    fig, axes = plt.subplots(1, len(norm_methods) + 1, figsize=(15, 4))
    fig.suptitle(f'QQ-plot مقایسه با توزیع نرمال - ستون: {sample_col}', fontsize=14)
    
    # داده اصلی
    clean_original = df[sample_col].dropna()
    if len(clean_original) > 3:
        stats.probplot(clean_original, dist="norm", plot=axes[0])
        axes[0].set_title(f'Original Data\np-value={normality_score(df[sample_col]):.4f}')
    
    # داده‌های نرمال‌شده
    for idx, (method_name, method_func) in enumerate(norm_methods.items(), start=1):
        transformed = method_func(df[sample_col].values)
        clean_transformed = transformed[~np.isnan(transformed)]
        if len(clean_transformed) > 3:
            stats.probplot(clean_transformed, dist="norm", plot=axes[idx])
            p_val = normality_score(transformed)
            axes[idx].set_title(f'{method_name}\np-value={p_val:.4f}')
    
    plt.tight_layout()
    plt.savefig(output_dir / 'qqplot_comparison.png', dpi=150)
    plt.show()
    print(f"نمودار در '{output_dir / 'qqplot_comparison.png'}' ذخیره شد.")

print("\nپردازش با موفقیت به پایان رسید!")
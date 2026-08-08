# پردازش داده های خارج از ردیف

import pandas as pd
import numpy as np
from scipy import stats

# جدول درونیابی برای ضریب g در روش دورفل
G_COEFFICIENTS = {
    4: 7.2, 5: 6, 6: 5.5, 7: 5.0, 8: 4.9, 9: 4.8, 10: 4.5, 15: 4.2, 20: 4.0, 
    25: 3.9, 30: 3.8, 40: 3.79, 50: 3.78, 60: 3.78, 70: 3.8, 80: 3.8, 
    90: 3.81, 100: 3.82, 150: 3.85, 200: 3.9, 225: 3.95, 250: 4.02, 400: 4.05, 
    500: 4.1, 600: 4.2, 700: 4.3, 800: 4.35, 900: 4.4, 1000:4.5
}

def get_g_coefficient(n):
    """دریافت ضریب g بر اساس تعداد نمونه با درونیابی"""
    if n <= 4:
        return G_COEFFICIENTS[4]
    elif n >= 1000:
        return G_COEFFICIENTS[1000]
    else:
        # پیدا کردن دو مقدار نزدیک‌تر
        keys = sorted(G_COEFFICIENTS.keys())
        lower = max([k for k in keys if k <= n])
        upper = min([k for k in keys if k >= n])
        
        if lower == upper:
            return G_COEFFICIENTS[lower]
        
        # محاسبه ضریب درونیابی
        g_lower = G_COEFFICIENTS[lower]
        g_upper = G_COEFFICIENTS[upper]
        
        # درونیابی خطی
        g = g_lower + (g_upper - g_lower) * (n - lower) / (upper - lower)
        return g

def detect_outliers_zscore(data, threshold=3):
    """تشخیص مقادیر خارج از رده با استفاده از روش Z-score"""
    z_scores = stats.zscore(data)
    outliers = np.abs(z_scores) > threshold
    
    # محاسبه مقادیر آستانه بالا و پایین
    mean = data.mean()
    std = data.std()
    upper_threshold = mean + threshold * std
    lower_threshold = mean - threshold * std
    
    # ایجاد آرایه مقادیر جایگزین
    replacement_values = pd.Series(index=data.index)
    replacement_values[z_scores > threshold] = upper_threshold
    replacement_values[z_scores < -threshold] = lower_threshold
    
    return outliers, replacement_values

def detect_outliers_iqr(data):
    """تشخیص مقادیر خارج از رده با استفاده از روش IQR"""
    Q1 = data.quantile(0.25)
    Q3 = data.quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    
    outliers = (data < lower_bound) | (data > upper_bound)
    
    # ایجاد آرایه مقادیر جایگزین
    replacement_values = pd.Series(index=data.index)
    replacement_values[data > upper_bound] = upper_bound
    replacement_values[data < lower_bound] = lower_bound
    
    return outliers, replacement_values

def detect_outliers_dorfel(data):
    """تشخیص مقادیر خارج از رده با استفاده از روش دورفل"""
    n = len(data)
    g = get_g_coefficient(n)
    
    # کپی از داده اصلی برای پردازش
    processed_data = data.copy()
    # مجموعه‌ای برای نگهداری مقادیر جایگزین شده
    replaced_indices = set()
    
    while True:
        # محاسبه میانگین و انحراف معیار بدون در نظر گرفتن مقادیر جایگزین شده
        temp_data = processed_data[~processed_data.index.isin(replaced_indices)]
        
        if len(temp_data) == 0:
            break
            
        # پیدا کردن ماکزیمم از داده‌های باقی‌مانده
        current_max = temp_data.max()
        max_indices = temp_data[temp_data == current_max].index
        
        # محاسبه میانگین و انحراف معیار بدون در نظر گرفتن ماکزیمم
        temp_data = temp_data[temp_data < current_max]
        
        if len(temp_data) == 0:
            break
            
        m = temp_data.mean()
        s = temp_data.std()
        n = len(temp_data)
        g = get_g_coefficient(n)
        threshold = m + g * s
        
        # بررسی وجود مقادیر بزرگتر از آستانه
        outliers = processed_data > threshold
        # حذف مقادیر قبلاً جایگزین شده از مجموعه outliers
        #outliers = outliers & ~processed_data.index.isin(replaced_indices)
        
        if current_max <=threshold:
            break
            
        # جایگزینی مقادیر خارج از رده با مقدار آستانه
        processed_data[outliers] = threshold
        # اضافه کردن شاخص‌های جایگزین شده به مجموعه
        replaced_indices.update(outliers[outliers].index)
    
    return processed_data

def process_outliers(file_path, sheet_name, method='iqr', threshold=3):
    """
    پردازش مقادیر خارج از رده با روش انتخابی
    
    پارامترها:
    file_path: مسیر فایل اکسل
    sheet_name: نام شیت
    method: روش تشخیص ('iqr', 'zscore', یا 'dorfel')
    threshold: آستانه برای روش Z-score
    """
    # خواندن فایل اکسل
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
    except Exception as e:
        print(f"خطا در خواندن فایل اکسل: {e}")
        return
    
    # کپی کردن داده‌ها برای پردازش
    processed_df = df.copy()
    
    # پردازش هر ستون عددی
    for column in processed_df.select_dtypes(include=[np.number]).columns:
        if method.lower() == 'zscore':
            outliers, replacement_values = detect_outliers_zscore(processed_df[column], threshold)
            processed_df.loc[outliers, column] = replacement_values[outliers]
        elif method.lower() == 'dorfel':
            processed_df[column] = detect_outliers_dorfel(processed_df[column].copy())
        else:  # روش پیش‌فرض IQR
            outliers, replacement_values = detect_outliers_iqr(processed_df[column])
            processed_df.loc[outliers, column] = replacement_values[outliers]
    
    # ذخیره نتایج در فایل جدید
    output_file = file_path.replace('.xlsx', f'_processed_{method}.xlsx')
    try:
        processed_df.to_excel(output_file, sheet_name=sheet_name, index=False)
        print(f"پردازش با روش {method} با موفقیت انجام شد.")
        print(f"نتایج در فایل {output_file} ذخیره شد.")
    except Exception as e:
        print(f"خطا در ذخیره فایل: {e}")

if __name__ == "__main__":
    file_path = input("نام فایل اکسل را وارد کنید: ")
    sheet_name = input("نام شیت مورد نظر را وارد کنید: ")
    
    print("\nروش‌های موجود برای تشخیص مقادیر خارج از رده:")
    print("1. روش IQR (فاصله بین چارکی)")
    print("2. روش Z-score ")
    print("3. روش دورفل (بازگشتی)")
    
    method_choice = input("\nشماره روش مورد نظر را وارد کنید (1، 2 یا 3): ")
    
    if method_choice == "2":
        threshold = float(input("آستانه Z-score را وارد کنید (پیش‌فرض: 3): ") or "3")
        process_outliers(file_path, sheet_name, method='zscore', threshold=threshold)
    elif method_choice == "3":
        process_outliers(file_path, sheet_name, method='dorfel')
    else:
        process_outliers(file_path, sheet_name, method='iqr')

    

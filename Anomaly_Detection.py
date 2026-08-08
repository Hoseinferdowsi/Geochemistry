import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# تنظیمات نمایش
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Tahoma', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ==================================================
# 1. خواندن فایل و شناسایی ستون‌ها
# ==================================================

def load_data(file_path):
    """خواندن فایل اکسل و شناسایی ستون‌های عددی"""
    df = pd.read_excel(file_path)
    
    # حذف ستون‌های غیرعددی (با استفاده از لیست کلمات کلیدی)
    excluded_keywords = ['name', 'id', 'sample', 'coord', 'x_', 'y_', 'easting', 'northing', 
                         'longitude', 'latitude', 'depth', 'date', 'remark', 'comment']
    
    numeric_cols = []
    for col in df.columns:
        col_lower = col.lower()
        # بررسی عددی بودن و عدم تطابق با کلمات کلیدی
        if pd.api.types.is_numeric_dtype(df[col]):
            if not any(keyword in col_lower for keyword in excluded_keywords):
                numeric_cols.append(col)
    
    # حذف ستون‌هایی با بیش از 80% داده缺失
    valid_cols = []
    for col in numeric_cols:
        if df[col].notna().sum() / len(df) > 0.2:
            valid_cols.append(col)
    
    print(f"📊 فایل خوانده شد: {df.shape[0]} نمونه, {len(valid_cols)} عنصر عددی معتبر")
    print(f"عناصر شناسایی شده: {valid_cols[:10]}{'...' if len(valid_cols) > 10 else ''}")
    
    return df, valid_cols

# ==================================================
# 2. روش میانگین ± انحراف معیار (Mean ± SD)
# ==================================================

def detect_anomalies_mean_sd(data, method='median', thresholds=[1, 2, 3]):
    """
    تشخیص آنومالی با روش میانگین ± انحراف معیار
    
    Parameters:
    -----------
    data : array
        داده‌های عنصر
    method : str
        'mean' برای میانگین یا 'median' برای میانه (مقاوم به outlier)
    thresholds : list
        ضرایب انحراف معیار (مثلاً [1, 2, 3])
    
    Returns:
    --------
    dict : شامل thresholds, anomalies, statistics
    """
    # حذف NaNها
    clean_data = data[~np.isnan(data)]
    
    if len(clean_data) < 4:
        return None
    
    # انتخاب شاخص مرکزی
    if method == 'median':
        center = np.median(clean_data)
        std = np.std(clean_data)
    else:
        center = np.mean(clean_data)
        std = np.std(clean_data)
    
    results = {}
    for threshold in thresholds:
        upper_limit = center + threshold * std
        lower_limit = center - threshold * std
        
        # شناسایی آنومالی‌ها
        high_anomalies = clean_data[clean_data > upper_limit]
        low_anomalies = clean_data[clean_data < lower_limit]
        
        results[threshold] = {
            'lower_limit': lower_limit,
            'upper_limit': upper_limit,
            'high_anomalies': high_anomalies,
            'low_anomalies': low_anomalies,
            'high_count': len(high_anomalies),
            'low_count': len(low_anomalies),
            'high_percent': 100 * len(high_anomalies) / len(clean_data),
            'low_percent': 100 * len(low_anomalies) / len(clean_data),
            'total_percent': 100 * (len(high_anomalies) + len(low_anomalies)) / len(clean_data)
        }
    
    return {
        'center': center,
        'std': std,
        'method': method,
        'results': results
    }

# ==================================================
# 3. روش غلظت-تعداد (Concentration-Number / C-N)
# ==================================================

def concentration_number_anomaly(data, min_bins=20, auto_select=True, target_percent=10):
    """
    تشخیص آنومالی با روش غلظت-تعداد (C-N)
    
    این روش بر اساس شکستگی در نمودار Log-Log غلظت و تعداد پیکسل‌ها عمل می‌کند
    
    Parameters:
    -----------
    data : array
        داده‌های عنصر
    min_bins : int
        حداقل تعداد bins برای هیستوگرام
    auto_select : bool
        انتخاب خودکار حد آستانه
    target_percent : float
        درصد تقریبی آنومالی (برای انتخاب خودکار)
    
    Returns:
    --------
    dict : شامل thresholds, breakpoints, anomaly_threshold
    """
    clean_data = data[~np.isnan(data)]
    
    if len(clean_data) < 10:
        return None
    
    # ایجاد هیستوگرام و محاسبه غلظت-تعداد
    hist, bin_edges = np.histogram(clean_data, bins=min_bins)
    
    # محاسبه مرکز bins
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    
    # محاسبه تعداد تجمعی (از بالا به پایین)
    cumulative_counts = np.cumsum(hist[::-1])[::-1]
    
    # حذف bins با تعداد صفر
    mask = cumulative_counts > 0
    log_concentration = np.log10(bin_centers[mask])
    log_cumulative = np.log10(cumulative_counts[mask])
    
    if len(log_concentration) < 5:
        return None
    
    # یافتن نقطه شکست با استفاده از روش قطعه‌ای خطی
    breakpoints = find_breakpoints(log_concentration, log_cumulative)
    
    # انتخاب حد آستانه مناسب
    if auto_select:
        # روش 1: بر اساس درصد داده‌ها
        sorted_data = np.sort(clean_data)
        percentile_idx = int(len(sorted_data) * (100 - target_percent) / 100)
        anomaly_threshold = sorted_data[percentile_idx]
        
        # روش 2: بر اساس شکستگی C-N
        if breakpoints:
            cn_threshold = 10 ** breakpoints[-1]
            # ترکیب دو روش
            anomaly_threshold = max(anomaly_threshold, cn_threshold)
    else:
        anomaly_threshold = 10 ** breakpoints[-1] if breakpoints else np.percentile(clean_data, 90)
    
    # شناسایی آنومالی‌ها
    anomalies = clean_data[clean_data > anomaly_threshold]
    
    # تشخیص چند سطح آنومالی (ضعیف، متوسط، قوی)
    anomaly_levels = {}
    percentiles = [90, 95, 98, 99]
    for p in percentiles:
        threshold = np.percentile(clean_data, p)
        level_anomalies = clean_data[clean_data > threshold]
        anomaly_levels[f'P{p}'] = {
            'threshold': threshold,
            'count': len(level_anomalies),
            'percent': 100 * len(level_anomalies) / len(clean_data)
        }
    
    return {
        'anomaly_threshold': anomaly_threshold,
        'anomalies': anomalies,
        'anomaly_count': len(anomalies),
        'anomaly_percent': 100 * len(anomalies) / len(clean_data),
        'breakpoints': breakpoints,
        'anomaly_levels': anomaly_levels,
        'log_concentration': log_concentration,
        'log_cumulative': log_cumulative
    }

def find_breakpoints(x, y, min_segment=5):
    """
    یافتن نقاط شکست در نمودار Log-Log با روش قطعه‌ای خطی
    """
    n = len(x)
    if n < min_segment * 2:
        return []
    
    best_break = None
    best_r2 = -np.inf
    
    # جستجو برای بهترین نقطه شکست
    for i in range(min_segment, n - min_segment):
        # قطعه اول
        x1, y1 = x[:i], y[:i]
        slope1, intercept1, r1, _, _ = stats.linregress(x1, y1)
        
        # قطعه دوم
        x2, y2 = x[i:], y[i:]
        slope2, intercept2, r2, _, _ = stats.linregress(x2, y2)
        
        # R2 ترکیبی وزنی
        r2_combined = (r1**2 * len(x1) + r2**2 * len(x2)) / n
        
        if r2_combined > best_r2:
            best_r2 = r2_combined
            best_break = i
    
    if best_break is not None:
        # بازگشت مختصات نقطه شکست
        return [x[best_break]]
    
    return []

# ==================================================
# 4. تابع اصلی برای آنومالی‌یابی تمام عناصر
# ==================================================

def analyze_all_elements(df, element_cols, output_dir='anomaly_analysis'):
    """
    تحلیل آنومالی برای تمام عناصر با دو روش
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    results_summary = []
    
    for element in element_cols:
        print(f"\n{'='*50}")
        print(f"تحلیل عنصر: {element}")
        print(f"{'='*50}")
        
        data = df[element].values
        
        # حذف NaN
        clean_data = data[~np.isnan(data)]
        if len(clean_data) < 10:
            print(f"⚠️ داده کافی نیست (تعداد: {len(clean_data)}) - رد شد")
            continue
        
        # آمار پایه
        stats_basic = {
            'count': len(clean_data),
            'min': clean_data.min(),
            'max': clean_data.max(),
            'mean': clean_data.mean(),
            'median': clean_data.median(),
            'std': clean_data.std(),
            'skew': stats.skew(clean_data),
            'kurtosis': stats.kurtosis(clean_data)
        }
        
        print(f"📊 آمار پایه: min={stats_basic['min']:.4f}, max={stats_basic['max']:.4f}, "
              f"mean={stats_basic['mean']:.4f}, median={stats_basic['median']:.4f}")
        print(f"   چولگی={stats_basic['skew']:.3f}, کورتوزیس={stats_basic['kurtosis']:.3f}")
        
        # ===== روش 1: میانگین ± انحراف معیار =====
        mean_sd_results = detect_anomalies_mean_sd(data, method='median', thresholds=[1, 2, 3])
        
        if mean_sd_results:
            print(f"\n📈 روش میانگین ± انحراف معیار (بر اساس میانه):")
            for thresh, res in mean_sd_results['results'].items():
                print(f"   {thresh}σ: بالای {res['upper_limit']:.4f} -> {res['high_count']} نمونه ({res['high_percent']:.1f}%)")
        
        # ===== روش 2: غلظت-تعداد (C-N) =====
        cn_results = concentration_number_anomaly(data, min_bins=20, target_percent=10)
        
        if cn_results:
            print(f"\n📈 روش غلظت-تعداد (C-N):")
            print(f"   حد آستانه آنومالی: {cn_results['anomaly_threshold']:.4f}")
            print(f"   تعداد آنومالی: {cn_results['anomaly_count']} ({cn_results['anomaly_percent']:.1f}%)")
            print(f"   سطوح آنومالی:")
            for level, info in cn_results['anomaly_levels'].items():
                print(f"     {level}: >{info['threshold']:.4f} -> {info['count']} نمونه ({info['percent']:.1f}%)")
        
        # ذخیره نتایج
        element_result = {
            'element': element,
            'count': stats_basic['count'],
            'min': stats_basic['min'],
            'max': stats_basic['max'],
            'mean': stats_basic['mean'],
            'median': stats_basic['median'],
            'std': stats_basic['std'],
            'skewness': stats_basic['skew'],
            'kurtosis': stats_basic['kurtosis']
        }
        
        # اضافه کردن نتایج روش‌ها
        if mean_sd_results:
            for thresh, res in mean_sd_results['results'].items():
                element_result[f'mean_sd_{thresh}σ_upper'] = res['upper_limit']
                element_result[f'mean_sd_{thresh}σ_high_count'] = res['high_count']
                element_result[f'mean_sd_{thresh}σ_high_percent'] = res['high_percent']
        
        if cn_results:
            element_result['cn_threshold'] = cn_results['anomaly_threshold']
            element_result['cn_anomaly_count'] = cn_results['anomaly_count']
            element_result['cn_anomaly_percent'] = cn_results['anomaly_percent']
            for level, info in cn_results['anomaly_levels'].items():
                element_result[f'cn_{level}_threshold'] = info['threshold']
                element_result[f'cn_{level}_percent'] = info['percent']
        
        results_summary.append(element_result)
        
        # رسم نمودارهای تشخیص آنومالی
        plot_anomaly_diagnostics(element, data, mean_sd_results, cn_results, output_dir)
    
    # ذخیره خلاصه نتایج
    summary_df = pd.DataFrame(results_summary)
    summary_path = output_dir / 'anomaly_detection_summary.xlsx'
    summary_df.to_excel(summary_path, index=False)
    print(f"\n✅ خلاصه نتایج ذخیره شد: {summary_path}")
    
    return summary_df

# ==================================================
# 5. رسم نمودارهای تشخیص آنومالی
# ==================================================

def plot_anomaly_diagnostics(element, data, mean_sd_results, cn_results, output_dir):
    """
    رسم نمودارهای تشخیص آنومالی برای یک عنصر
    """
    clean_data = data[~np.isnan(data)]
    
    if len(clean_data) < 10:
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(f'Anomaly Detection Analysis - {element}', fontsize=14, fontweight='bold')
    
    # 1. هیستوگرام با حدود آنومالی
    ax1 = axes[0, 0]
    ax1.hist(clean_data, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
    ax1.set_xlabel('Concentration (ppm or %)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Histogram with Anomaly Thresholds')
    
    # اضافه کردن خطوط Mean±SD
    if mean_sd_results:
        center = mean_sd_results['center']
        ax1.axvline(center, color='green', linestyle='--', linewidth=2, label=f"Median={center:.2f}")
        
        colors = ['orange', 'red', 'darkred']
        for i, (thresh, res) in enumerate(mean_sd_results['results'].items()):
            ax1.axvline(res['upper_limit'], color=colors[i], linestyle=':', 
                       linewidth=2, label=f"{thresh}σ Upper={res['upper_limit']:.2f}")
    
    # اضافه کردن خط C-N
    if cn_results:
        ax1.axvline(cn_results['anomaly_threshold'], color='purple', 
                   linestyle='-', linewidth=2, label=f"C-N Threshold={cn_results['anomaly_threshold']:.2f}")
    
    ax1.legend()
    
    # 2. نمودار جعبه‌ای (Boxplot)
    ax2 = axes[0, 1]
    bp = ax2.boxplot(clean_data, vert=True, patch_artist=True)
    bp['boxes'][0].set_facecolor('lightblue')
    ax2.set_ylabel('Concentration')
    ax2.set_title('Boxplot with Outliers')
    ax2.grid(True, alpha=0.3)
    
    # 3. نمودار غلظت-تعداد (C-N Plot)
    ax3 = axes[1, 0]
    if cn_results and 'log_concentration' in cn_results:
        ax3.plot(cn_results['log_concentration'], cn_results['log_cumulative'], 
                'o-', markersize=4, linewidth=1)
        
        # علامت‌گذاری نقاط شکست
        if cn_results['breakpoints']:
            for bp in cn_results['breakpoints']:
                idx = np.argmin(np.abs(cn_results['log_concentration'] - bp))
                ax3.plot(bp, cn_results['log_cumulative'][idx], 'ro', markersize=10)
                ax3.axvline(bp, color='red', linestyle='--', alpha=0.5)
        
        ax3.set_xlabel('Log(Concentration)')
        ax3.set_ylabel('Log(Cumulative Frequency)')
        ax3.set_title('Concentration-Number (C-N) Plot')
        ax3.grid(True, alpha=0.3)
    
    # 4. نمودار QQ-plot برای بررسی نرمال بودن
    ax4 = axes[1, 1]
    stats.probplot(clean_data, dist="norm", plot=ax4)
    ax4.set_title(f'Q-Q Plot (Skewness={stats.skew(clean_data):.3f})')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / f'{element}_anomaly_diagnostics.png', dpi=150, bbox_inches='tight')
    plt.close()

# ==================================================
# 6. رسم نقشه آنومالی (اگر مختصات موجود باشد)
# ==================================================

def plot_anomaly_maps(df, element_cols, anomaly_results, x_col=None, y_col=None, output_dir='anomaly_analysis'):
    """
    رسم نقشه پراکنش آنومالی‌ها روی نقشه (در صورت وجود مختصات)
    """
    # تلاش برای یافتن ستون‌های مختصات
    if x_col is None or y_col is None:
        x_keywords = ['x', 'easting', 'utm_x', 'longitude']
        y_keywords = ['y', 'northing', 'utm_y', 'latitude']
        
        for col in df.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in x_keywords):
                if x_col is None and pd.api.types.is_numeric_dtype(df[col]):
                    x_col = col
            if any(k in col_lower for k in y_keywords):
                if y_col is None and pd.api.types.is_numeric_dtype(df[col]):
                    y_col = col
    
    if x_col is None or y_col is None:
        print("⚠️ مختصات برای رسم نقشه آنومالی یافت نشد")
        return
    
    output_dir = Path(output_dir)
    maps_dir = output_dir / 'anomaly_maps'
    maps_dir.mkdir(exist_ok=True)
    
    # حذف ردیف‌های بدون مختصات
    valid_coords = df[x_col].notna() & df[y_col].notna()
    if valid_coords.sum() < 5:
        print("⚠️ داده مختصات کافی برای رسم نقشه وجود ندارد")
        return
    
    for element in element_cols[:10]:  # حداکثر 10 عنصر برای نقشه
        data = df[element].values
        
        # تشخیص آنومالی با روش C-N
        cn_results = concentration_number_anomaly(data, target_percent=10)
        
        if cn_results is None:
            continue
        
        # علامت‌گذاری آنومالی‌ها
        anomaly_mask = data > cn_results['anomaly_threshold']
        background_mask = ~anomaly_mask & ~np.isnan(data)
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # رسم نقاط پس‌زمینه
        bg_x = df.loc[background_mask & valid_coords, x_col].values
        bg_y = df.loc[background_mask & valid_coords, y_col].values
        bg_values = data[background_mask & valid_coords]
        
        scat_bg = ax.scatter(bg_x, bg_y, c=bg_values, s=30, 
                            cmap='viridis', alpha=0.6, edgecolors='gray', 
                            linewidth=0.5, label='Background')
        
        # رسم آنومالی‌ها (با رنگ قرمز و سایز بزرگتر)
        an_x = df.loc[anomaly_mask & valid_coords, x_col].values
        an_y = df.loc[anomaly_mask & valid_coords, y_col].values
        an_values = data[anomaly_mask & valid_coords]
        
        scat_an = ax.scatter(an_x, an_y, c='red', s=100, marker='^', 
                            edgecolors='black', linewidth=1, 
                            label=f'Anomalies ({len(an_x)} samples)', zorder=5)
        
        # اضافه کردن label برای مقادیر آنومالی
        for i, (x, y, val) in enumerate(zip(an_x, an_y, an_values)):
            ax.annotate(f'{val:.1f}', (x, y), xytext=(5, 5), 
                       textcoords='offset points', fontsize=8, alpha=0.7)
        
        ax.set_xlabel(f'X Coordinate ({x_col})')
        ax.set_ylabel(f'Y Coordinate ({y_col})')
        ax.set_title(f'{element} - Anomaly Map (C-N Method)\nThreshold={cn_results["anomaly_threshold"]:.2f}')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # colorbar برای پس‌زمینه
        cbar = plt.colorbar(scat_bg, ax=ax)
        cbar.set_label('Concentration (ppm or %)')
        
        plt.tight_layout()
        plt.savefig(maps_dir / f'{element}_anomaly_map.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    print(f"✅ نقشه‌های آنومالی در {maps_dir} ذخیره شدند")

# ==================================================
# 7. تابع اصلی
# ==================================================

def main():
    # مسیر فایل
    file_path = Path('D:/03_AI/AI_Programming/Geochemistry_v3.1/Data/Kashmar_censored_processed.xlsx')
    
    # خواندن داده
    df, element_cols = load_data(file_path)
    
    if len(element_cols) == 0:
        print("❌ هیچ عنصر عددی معتبری یافت نشد!")
        return
    
    # انتخاب عناصر برای آنالیز
    print(f"\n🎯 {len(element_cols)} عنصر برای تحلیل آنومالی موجود است.")
    
    analyze_all = input("آیا همه عناصر تحلیل شوند؟ (y/n) [پیش‌فرض: y]: ").strip().lower()
    
    if analyze_all == 'n':
        elem_input = input("نام عناصر مورد نظر (با کاما جدا کنید): ")
        elements_to_analyze = [e.strip() for e in elem_input.split(',')]
        elements_to_analyze = [e for e in elements_to_analyze if e in element_cols]
    else:
        elements_to_analyze = element_cols
    
    if not elements_to_analyze:
        print("❌ عنصر معتبری انتخاب نشد!")
        return
    
    # تحلیل آنومالی
    summary_df = analyze_all_elements(df, elements_to_analyze, output_dir='anomaly_analysis')
    
    # رسم نقشه‌های آنومالی (در صورت وجود مختصات)
    plot_anomaly_maps(df, elements_to_analyze, summary_df, output_dir='anomaly_analysis')
    
    # نمایش خلاصه
    print("\n" + "="*60)
    print("📊 خلاصه نتایج آنومالی‌یابی:")
    print("="*60)
    
    for _, row in summary_df.iterrows():
        print(f"\n🔹 {row['element']}:")
        print(f"   میانگین: {row['mean']:.2f}, میانه: {row['median']:.2f}")
        
        if 'cn_anomaly_count' in row:
            print(f"   روش C-N: {row['cn_anomaly_count']} آنومالی ({row['cn_anomaly_percent']:.1f}%) - آستانه: {row['cn_threshold']:.2f}")
        
        if 'mean_sd_2σ_high_count' in row:
            print(f"   روش 2σ: {row['mean_sd_2σ_high_count']} آنومالی ({row['mean_sd_2σ_high_percent']:.1f}%) - آستانه: {row['mean_sd_2σ_upper']:.2f}")
    
    print("\n✅ فرآیند آنومالی‌یابی با موفقیت به پایان رسید!")

# ==================================================
# اجرا
# ==================================================

if __name__ == "__main__":
    main()
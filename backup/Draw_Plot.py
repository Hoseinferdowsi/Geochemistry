import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, PowerNorm
from scipy.interpolate import griddata
from scipy.spatial import cKDTree
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# تنظیمات نمایش و فونت فارسی (اختیاری)
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Tahoma', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ==================================================
# 1. خواندن فایل اکسل و شناسایی ستون‌ها
# ==================================================

def load_and_identify_columns(file_path):
    """
    خواندن فایل اکسل و شناسایی خودکار:
    - ستون مختصات X و Y
    - ستون‌های غیرعددی (شناسه نمونه)
    - ستون‌های عددی (عناصر و سایر پارامترها)
    """
    df = pd.read_excel(file_path)
    
    print(f"فایل خوانده شد: {df.shape[0]} نمونه, {df.shape[1]} متغیر")
    print("\nستون‌های موجود:")
    for i, col in enumerate(df.columns):
        print(f"  {i+1}. {col} (نوع: {df[col].dtype})")
    
    # لیست کلمات کلیدی برای شناسایی مختصات
    x_keywords = ['x', 'x_coord', 'x_coordinate', 'easting', 'utm_x', 'longitude', 'lon', 'x_utm', 'x utm', 'x coord']
    y_keywords = ['y', 'y_coord', 'y_coordinate', 'northing', 'utm_y', 'latitude', 'lat', 'y_utm', 'y utm', 'y coord']
    
    # شناسایی خودکار ستون‌های مختصات
    x_col = None
    y_col = None
    
    for col in df.columns:
        col_lower = col.lower().strip()
        if any(keyword in col_lower for keyword in x_keywords):
            if x_col is None:
                x_col = col
        if any(keyword in col_lower for keyword in y_keywords):
            if y_col is None:
                y_col = col
    
    # اگر خودکار شناسایی نشد، از کاربر بپرس
    if x_col is None or y_col is None:
        print("\n⚠️ ستون‌های مختصات به صورت خودکار شناسایی نشدند.")
        print(f"شناسایی شده: X={x_col}, Y={y_col}")
        
        print("\nلطفاً ستون‌های مختصات را مشخص کنید:")
        for i, col in enumerate(df.columns):
            print(f"  {i}. {col}")
        
        try:
            x_idx = int(input("شماره ستون X: "))
            y_idx = int(input("شماره ستون Y: "))
            x_col = df.columns[x_idx]
            y_col = df.columns[y_idx]
        except:
            print("خطا در انتخاب! از ۵ ستون اول به عنوان مختصات استفاده می‌شود.")
            x_col = df.columns[0]
            y_col = df.columns[1]
    
    # شناسایی ستون‌های غیرعددی (شناسه نمونه)
    non_numeric_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    string_cols = [col for col in non_numeric_cols if col not in [x_col, y_col]]
    
    # شناسایی ستون‌های عددی (عناصر و سایر متغیرها)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # حذف مختصات از لیست عناصر
    element_cols = [col for col in numeric_cols if col not in [x_col, y_col]]
    
    print(f"\n✅ ستون X شناسایی شد: {x_col}")
    print(f"✅ ستون Y شناسایی شد: {y_col}")
    print(f"📊 ستون‌های عددی (عناصر): {len(element_cols)} ستون")
    print(f"🏷️ ستون‌های غیرعددی (شناسه): {len(string_cols)} ستون - {string_cols}")
    
    return df, x_col, y_col, element_cols, string_cols

# ==================================================
# 2. توابع درون‌یابی (Interpolation)
# ==================================================

def create_grid(x, y, values, grid_size=100, method='linear'):
    """
    ایجاد شبکه منظم و درون‌یابی داده‌ها
    
    Parameters:
    -----------
    x, y : array
        مختصات نقاط
    values : array
        مقادیر عنصر
    grid_size : int
        اندازه شبکه (grid_size x grid_size)
    method : str
        روش درون‌یابی: 'linear', 'cubic', 'nearest'
    """
    # حذف مقادیر NaN
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean = x[mask]
    y_clean = y[mask]
    values_clean = values[mask]
    
    if len(x_clean) < 4:
        print(f"⚠️ داده کافی برای درون‌یابی وجود ندارد ({len(x_clean)} نقطه)")
        return None, None, None
    
    # تعیین محدوده شبکه
    x_min, x_max = x_clean.min(), x_clean.max()
    y_min, y_max = y_clean.min(), y_clean.max()
    
    # افزودن حاشیه 5%
    x_padding = (x_max - x_min) * 0.05
    y_padding = (y_max - y_min) * 0.05
    
    x_min -= x_padding
    x_max += x_padding
    y_min -= y_padding
    y_max += y_padding
    
    # ایجاد شبکه منظم
    xi = np.linspace(x_min, x_max, grid_size)
    yi = np.linspace(y_min, y_max, grid_size)
    xi, yi = np.meshgrid(xi, yi)
    
    # درون‌یابی
    try:
        zi = griddata((x_clean, y_clean), values_clean, (xi, yi), method=method)
    except:
        # fallback به nearest
        zi = griddata((x_clean, y_clean), values_clean, (xi, yi), method='nearest')
    
    return xi, yi, zi

def idw_interpolation(x, y, values, grid_size=100, power=2):
    """
    درون‌یابی Inverse Distance Weighting (IDW)
    مناسب برای داده‌های زمین‌شیمیایی
    """
    # حذف مقادیر NaN
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean = x[mask]
    y_clean = y[mask]
    values_clean = values[mask]
    
    if len(x_clean) < 4:
        return None, None, None
    
    # تعیین محدوده شبکه
    x_min, x_max = x_clean.min(), x_clean.max()
    y_min, y_max = y_clean.min(), y_clean.max()
    
    x_padding = (x_max - x_min) * 0.05
    y_padding = (y_max - y_min) * 0.05
    
    x_min -= x_padding
    x_max += x_padding
    y_min -= y_padding
    y_max += y_padding
    
    # ایجاد شبکه منظم
    xi = np.linspace(x_min, x_max, grid_size)
    yi = np.linspace(y_min, y_max, grid_size)
    xi, yi = np.meshgrid(xi, yi)
    
    # محاسبه IDW
    zi = np.zeros_like(xi)
    
    for i in range(grid_size):
        for j in range(grid_size):
            distances = np.sqrt((xi[i, j] - x_clean)**2 + (yi[i, j] - y_clean)**2)
            weights = 1.0 / (distances**power + 1e-10)
            weights_sum = weights.sum()
            if weights_sum > 0:
                zi[i, j] = np.sum(values_clean * weights) / weights_sum
            else:
                zi[i, j] = np.nan
    
    return xi, yi, zi

# ==================================================
# 3. رسم نقشه توزیع عنصر
# ==================================================

def plot_element_map(x, y, values, element_name, xi=None, yi=None, zi=None, 
                     output_dir='element_maps', cmap='viridis', 
                     interpolation_method='idw', show_points=True):
    """
    رسم نقشه توزیع یک عنصر
    """
    fig, axes = plt.subplots(1, 2 if show_points else 1, figsize=(14, 6))
    
    if not show_points:
        axes = [axes]
    
    # حذف مقادیر NaN برای نمایش نقاط
    mask = ~(np.isnan(x) | np.isnan(y) | np.isnan(values))
    x_clean = x[mask]
    y_clean = y[mask]
    values_clean = values[mask]
    
    # تعیین مقیاس رنگی مناسب
    vmin = np.nanpercentile(values_clean, 5)
    vmax = np.nanpercentile(values_clean, 95)
    
    if vmin == vmax:
        vmin = values_clean.min()
        vmax = values_clean.max()
    
    # ===== نقشه درون‌یابی شده =====
    if xi is not None and zi is not None:
        # انتخاب colormap مناسب
        if cmap == 'auto':
            # بر اساس دامنه مقادیر
            if values_clean.max() / (values_clean.min() + 1e-10) > 100:
                cmap_choice = 'plasma'
                norm = LogNorm(vmin=max(vmin, 0.001), vmax=vmax)
            else:
                cmap_choice = 'viridis'
                norm = None
        else:
            cmap_choice = cmap
            norm = None
        
        im = axes[0].contourf(xi, yi, zi, levels=20, cmap=cmap_choice, 
                              norm=norm, alpha=0.9)
        plt.colorbar(im, ax=axes[0], label=f'{element_name} (ppm or %)')
        
        # اضافه کردن نقاط نمونه
        if show_points:
            scat = axes[0].scatter(x_clean, y_clean, c=values_clean, 
                                   s=30, edgecolor='black', linewidth=0.5,
                                   cmap=cmap_choice, norm=norm, zorder=5)
        
        axes[0].set_xlabel('X Coordinate (m)')
        axes[0].set_ylabel('Y Coordinate (m)')
        axes[0].set_title(f'{element_name} - Interpolated Map (Method: {interpolation_method})')
        axes[0].grid(True, alpha=0.3)
    
    # ===== نقشه نقاط (Bubble plot) =====
    if show_points:
        # نرمال‌سازی سایز حباب‌ها
        sizes = 20 + 80 * (values_clean - values_clean.min()) / (values_clean.max() - values_clean.min() + 1e-10)
        
        scat2 = axes[1].scatter(x_clean, y_clean, s=sizes, c=values_clean, 
                                cmap=cmap_choice, edgecolor='black', linewidth=0.5,
                                alpha=0.7)
        plt.colorbar(scat2, ax=axes[1], label=f'{element_name} (ppm or %)')
        
        axes[1].set_xlabel('X Coordinate (m)')
        axes[1].set_ylabel('Y Coordinate (m)')
        axes[1].set_title(f'{element_name} - Sample Locations (Bubble size = concentration)')
        axes[1].grid(True, alpha=0.3)
    
    plt.suptitle(f'Distribution Map of {element_name}', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    # ذخیره نقشه
    output_path = output_dir / f'{element_name}_map.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_path

# ==================================================
# 4. نقشه حرارتی همبستگی عناصر (Correlation Heatmap)
# ==================================================

def plot_correlation_heatmap(df, element_cols, output_dir):
    """
    رسم نقشه حرارتی همبستگی بین عناصر
    """
    if len(element_cols) < 2:
        return
    
    corr_matrix = df[element_cols].corr()
    
    plt.figure(figsize=(12, 10))
    
    # ماسک برای مثلث بالایی
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    
    # رسم heatmap
    sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', 
                cmap='RdBu_r', center=0, square=True,
                linewidths=0.5, cbar_kws={"shrink": 0.8})
    
    plt.title('Element Correlation Heatmap', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    
    output_path = output_dir / 'correlation_heatmap.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✅ نقشه همبستگی ذخیره شد: {output_path}")

# ==================================================
# 5. تابع اصلی
# ==================================================

def main():
    # مسیر فایل
    file_path = Path('D:/03_AI/AI_Programming/Geochemistry_v3.1/Data/Kashmar_censored_processed.xlsx')
    
    # ایجاد دایرکتوری خروجی
    output_dir = Path('element_distribution_maps')
    output_dir.mkdir(exist_ok=True)
    
    # خواندن داده
    df, x_col, y_col, element_cols, string_cols = load_and_identify_columns(file_path)
    
    # نمایش آمار مختصات
    print(f"\n📐 محدوده مختصات:")
    print(f"   X: [{df[x_col].min():.2f}, {df[x_col].max():.2f}]")
    print(f"   Y: [{df[y_col].min():.2f}, {df[y_col].max():.2f}]")
    
    # حذف ردیف‌های با مختصات NaN
    initial_count = len(df)
    df = df.dropna(subset=[x_col, y_col])
    print(f"\n🧹 حذف {initial_count - len(df)} ردیف با مختصات نامعتبر")
    
    # دریافت مختصات و تبدیل به numpy array
    x_coords = df[x_col].values
    y_coords = df[y_col].values
    
    # انتخاب روش درون‌یابی
    print("\n" + "="*50)
    print("روش‌های درون‌یابی موجود:")
    print("  1. IDW (Inverse Distance Weighting) - پیشنهادی برای داده‌های زمین‌شیمی")
    print("  2. Linear - درون‌یابی خطی")
    print("  3. Cubic - درون‌یابی مکعبی (نرم‌تر)")
    print("  4. Nearest - نزدیک‌ترین همسایه")
    
    interp_choice = input("\nروش مورد نظر را انتخاب کنید (1-4) [پیش‌فرض: 1]: ").strip()
    
    interp_methods = {
        '1': ('idw', 'IDW'),
        '2': ('linear', 'Linear'),
        '3': ('cubic', 'Cubic'),
        '4': ('nearest', 'Nearest')
    }
    
    method_key, method_name = interp_methods.get(interp_choice, ('idw', 'IDW'))
    
    # انتخاب colormap
    print("\n🎨 Colormap options:")
    print("  auto - انتخاب خودکار بر اساس دامنه مقادیر")
    print("  viridis - سبز-آبی-زرد (پیش‌فرض)")
    print("  plasma - بنفش-زرد (مناسب برای داده‌های چوله)")
    print("  hot - قرمز-زرد-سفید")
    print("  coolwarm - آبی-سفید-قرمز")
    
    cmap_choice = input("\nColormap مورد نظر [پیش‌فرض: auto]: ").strip()
    if cmap_choice == '':
        cmap_choice = 'auto'
    
    # دریافت لیست عناصر برای رسم
    print(f"\n📊 {len(element_cols)} عنصر یافت شد:")
    for i, elem in enumerate(element_cols[:20]):
        print(f"  {i+1}. {elem}")
    if len(element_cols) > 20:
        print(f"  ... و {len(element_cols)-20} عنصر دیگر")
    
    plot_all = input("\nآیا همه عناصر رسم شوند؟ (y/n) [پیش‌فرض: y]: ").strip().lower()
    
    if plot_all == 'n':
        elem_input = input("نام عناصر مورد نظر (با کاما جدا کنید): ")
        elements_to_plot = [e.strip() for e in elem_input.split(',')]
        elements_to_plot = [e for e in elements_to_plot if e in element_cols]
    else:
        elements_to_plot = element_cols
    
    if not elements_to_plot:
        print("⚠️ هیچ عنصر معتبری انتخاب نشد!")
        return
    
    # رسم نقشه برای هر عنصر
    print(f"\n🎨 شروع رسم {len(elements_to_plot)} نقشه...")
    
    successful_maps = []
    
    for i, element in enumerate(elements_to_plot, 1):
        print(f"  {i}/{len(elements_to_plot)}: {element} ...", end=' ')
        
        values = df[element].values
        
        # بررسی داده‌های کافی
        valid_data = ~np.isnan(values)
        if valid_data.sum() < 4:
            print(f"⚠️ داده کافی نیست ({valid_data.sum()} نقطه) - رد شد")
            continue
        
        # درون‌یابی
        if method_key == 'idw':
            xi, yi, zi = idw_interpolation(x_coords, y_coords, values, grid_size=100)
        else:
            xi, yi, zi = create_grid(x_coords, y_coords, values, grid_size=100, method=method_key)
        
        # رسم نقشه
        try:
            output_path = plot_element_map(
                x_coords, y_coords, values, element,
                xi=xi, yi=yi, zi=zi,
                output_dir=output_dir,
                cmap=cmap_choice,
                interpolation_method=method_name,
                show_points=True
            )
            successful_maps.append(element)
            print(f"✓ ذخیره شد")
        except Exception as e:
            print(f"✗ خطا: {str(e)[:50]}")
    
    # رسم نقشه همبستگی
    if len(successful_maps) >= 2:
        print("\n📊 رسم نقشه همبستگی عناصر...")
        plot_correlation_heatmap(df, successful_maps, output_dir)
    
    # گزارش نهایی
    print("\n" + "="*50)
    print("✅ فرآیند با موفقیت به پایان رسید!")
    print(f"📁 نقشه‌ها در دایرکتوری '{output_dir}' ذخیره شدند.")
    print(f"🎯 تعداد نقشه‌های رسم شده: {len(successful_maps)}/{len(elements_to_plot)}")
    
    # نمایش فایل‌های خروجی
    if successful_maps:
        print("\n📋 فایل‌های ایجاد شده:")
        for f in sorted(output_dir.glob('*.png')):
            print(f"  - {f.name}")

# ==================================================
# اجرای برنامه
# ==================================================

if __name__ == "__main__":
    main()
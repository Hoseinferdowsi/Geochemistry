# ⚠️ منسوخ - فقط برای ارجاع.
# منطق وباپ اصلی در processing_services.py (process_censored_data) است.
# توجه: ضریب right_coe در این فایل 1.33 ولی در وب‌اپ 1.25 است؛
# اجرای این اسکریپت مستقل خروجی متفاوتی با وباپ می‌دهد.
import pandas as pd
import re

def process_excel(file_path, sheet_name):
    # خواندن شیت مورد نظر
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
    
    left_coe=0.75
    right_coe=1.33
    # تابع برای اصلاح مقادیر سلول
    def fix_value(val):
        if isinstance(val, str):
            # جستجوی <عدد یا >عدد
            match = re.match(r'([<>])\s*(\d+(\.\d+)?)', val)
            if match:
                sign = match.group(1)
                number = float(match.group(2))
                if sign == '<':
                    return number * left_coe
                elif sign == '>':
                    return number * right_coe
        return val

    # اعمال تابع به کل دیتافریم
    df = df.applymap(fix_value)
    
    # ذخیره فایل اصلاح شده
    output_path = file_path.replace('.xlsx', '_fixed.xlsx')
    df.to_excel(output_path, index=False)
    print(f"فایل اصلاح شده ذخیره شد: {output_path}")

# process_excel('your_file.xlsx', 'Sheet1')
if __name__ == "__main__":
    file_path = input("نام فایل اکسل را وارد کنید: ")
    sheet_name = input("نام شیت مورد نظر را وارد کنید: ")
    process_excel(file_path, sheet_name)
    
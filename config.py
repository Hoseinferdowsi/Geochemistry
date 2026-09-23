# -*- coding: utf-8 -*-
"""پیکربندی مرکزی پروژه Geochemistry Analysis.

تمام مقادیر ثابت پراکنده در کد از این‌جا خوانده می‌شوند و همگی
قابل بازنویسی با متغیرهای محیطی (Environment Variables) هستند.
"""
import secrets

# ── سرور ──
HOST = __import__('os').environ.get('APP_HOST', '127.0.0.1')
PORT = int(__import__('os').environ.get('APP_PORT', 5001))
DEBUG = __import__('os').environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')

# کلید session فلش: از متغیر محیطی، وگرنه تصادفی برای dev
SECRET_KEY = __import__('os').environ.get('SECRET_KEY') or secrets.token_hex(32)

# ── مسیرها و محدودیت‌ها ──
UPLOAD_FOLDER = __import__('os').environ.get('UPLOAD_FOLDER', 'uploads')
OUTPUT_FOLDER = 'output'
SESSIONS_FOLDER = __import__('os').environ.get('SESSIONS_FOLDER', 'sessions')
TEMPLATES_FOLDER = 'templates'
MAX_CONTENT_MB = int(__import__('os').environ.get('MAX_CONTENT_MB', 32))
MAX_CONTENT_LENGTH = MAX_CONTENT_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# ── ضرایب پیش‌فرض پردازش سانسور ──
# '<x' → x × CENSOR_LEFT_COEFFICIENT | '>x' → x × CENSOR_RIGHT_COEFFICIENT
CENSOR_LEFT_COEFFICIENT = float(__import__('os').environ.get('CENSOR_LEFT_COE', 0.75))
CENSOR_RIGHT_COEFFICIENT = float(__import__('os').environ.get('CENSOR_RIGHT_COE', 1.25))

# ── پاک‌سازی خودکار جلسات قدیمی ──
SESSION_TTL_DAYS = float(__import__('os').environ.get('SESSION_TTL_DAYS', 7))
CLEANUP_INTERVAL_HOURS = float(__import__('os').environ.get('CLEANUP_INTERVAL_HOURS', 6))

# ── درون‌یابی نقشه‌ها ──
IDW_DEFAULT_K = int(__import__('os').environ.get('IDW_DEFAULT_K', 12))  # همسایه‌های IDW (پیشنهادی ۸ تا ۱۵)
IDW_GRID_SIZE = 100
IDW_POWER = 2

# ── کریجینگ (pykrige) ──
KRIGING_METHOD = __import__('os').environ.get('KRIGING_METHOD', 'ordinary')  # ordinary | universal
KRIGING_VARIOGRAM = __import__('os').environ.get('KRIGING_VARIOGRAM', 'spherical')  # spherical | exponential | gaussian | linear
KRIGING_N_LAGS = int(__import__('os').environ.get('KRIGING_N_LAGS', 6))  # تعداد لگ واریوگرام (کم = سریع‌تر)
KRIGING_GRID_SIZE = int(__import__('os').environ.get('KRIGING_GRID_SIZE', 60))  # ابعاد گرید (کریجینگ سنگین‌تر است)

import sys
import os

# إضافة المجلد الرئيسي للمشروع إلى مسار البايثون
path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if path not in sys.path:
    sys.path.append(path)

try:
    from main import app
except Exception as e:
    # طباعة الخطأ في السجلات للتأكد
    print(f"Error importing app: {e}")
    raise e
import sys
import os

# إضافة المجلد الرئيسي للمشروع إلى مسارات النظام
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
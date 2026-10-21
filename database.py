import os
from supabase import create_client, Client
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("تحقق من إعدادات Supabase URL و Key في ملف البيئة (.env)")

# إنشاء عميل Supabase للاتصال بقاعدة البيانات
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
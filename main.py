from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from routers import auth, tenants, documents, rag, audit_logs # تم استيراد الراوترات الخاصة بالـ auth والـ tenants معاً

app = FastAPI(
    title="AI & RAG Platform Backend",
    version="1.0.0",
    description="Backend API for Graduation Project - FastAPI & Supabase"
)

# 🌐 إعدادات الـ CORS للسماح للفرونت إند بالاتصال
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # في الإنتاج يفضل تحديد نطاق الفرونت إند بدقة
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚀 تسجيل وتفعيل مسارات الـ APIs (Endpoints)
app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(rag.router)
app.include_router(audit_logs.router)

# 🏠 مسار تجريبي للتأكد أن السيرفر يعمل
@app.get("/")
def read_root():
    return {
        "status": "success",
        "message": "AI & RAG Backend is running successfully!",
        "database": "Connected to Supabase"
    }

# 🔍 مسار تجريبي للتحقق من الاتصال بقاعدة البيانات
@app.get("/api/v1/health-check")
def health_check():
    try:
        response = supabase.table("tenants").select("*").execute()
        return {
            "status": "healthy",
            "database_connection": "OK",
            "tenants_count": len(response.data)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
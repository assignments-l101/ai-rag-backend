from fastapi import APIRouter, Depends, HTTPException, Header
from database import supabase

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# 🛡️ دالة التحقق من الـ JWT واستخراج المستخدم
async def get_current_user(authorization: str = Header(...)):
    try:
        # استخراج التوكن من ترويسة الطلب (Bearer Token)
        token = authorization.split(" ")[1]
        
        # التحقق من صحة التتوكن عبر Supabase Auth
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
            
        return user_response.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# 👤 مسار جلب معلومات المستخدم الحالي وحالة الـ Tenant
@router.get("/me")
def get_user_profile(user = Depends(get_current_user)):
    try:
        user_id = user.id
        
        # 1. البحث عما إذا كان المستخدم منضمًا إلى مؤسسة في جدول العضويات
        membership = supabase.table("tenant_members").select("*").eq("user_id", user_id).execute()
        
        has_tenant = False
        tenant_id = None
        role = None
        
        if membership.data and len(membership.data) > 0:
            has_tenant = True
            tenant_id = membership.data[0]["tenant_id"]
            role = membership.data[0]["role"]
            
        return {
            "id": user_id,
            "email": user.email,
            "has_tenant": has_tenant,
            "tenant_id": tenant_id,
            "role": role
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from database import supabase

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# نموذج بيانات التسجيل
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_name: str

# نموذج بيانات تسجيل الدخول
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# 🛡️ دالة التحقق من الـ JWT واستخراج المستخدم
async def get_current_user(authorization: str = Header(...)):
    try:
        # استخراج التوكن من ترويسة الطلب (Bearer Token)
        token = authorization.split(" ")[1]
        
        # التحقق من صحة التوكن عبر Supabase Auth
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
            
        return user_response.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# 📝 مسار تسجيل حساب جديد (مع إنشاء المؤسسة وربطها تلقائياً)
@router.post("/signup")
def signup(payload: SignupRequest):
    try:
        # 1. إنشاء المستخدم في Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {
                "data": {"full_name": payload.name}
            }
        })
        
        if not auth_response or not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create user in auth system")
            
        user_id = auth_response.user.id
        
        # 2. إنشاء المؤسسة الجديدة في جدول tenants
        tenant_res = supabase.table("tenants").insert({
            "name": payload.organization_name
        }).execute()
        
        if not tenant_res.data or len(tenant_res.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create organization/tenant")
            
        tenant_id = tenant_res.data[0]["id"]
        
        # 3. ربط المستخدم بالمؤسسة في جدول tenant_members بدور admin
        member_res = supabase.table("tenant_members").insert({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": "admin"
        }).execute()
        
        # جلب التوكن إذا تم تسجيل الدخول مباشرة بعد التسجيل
        access_token = auth_response.session.access_token if auth_response.session else "mock_or_pending_token"

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "name": payload.name,
                "email": payload.email,
                "role": "admin",
                "tenant_id": tenant_id,
                "organization": payload.organization_name
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 🔑 مسار تسجيل الدخول
@router.post("/login")
def login(payload: LoginRequest):
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password
        })
        
        if not auth_response or not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        user = auth_response.user
        access_token = auth_response.session.access_token
        
        # جلب معلومات الـ Tenant الخاصة بالمستخدم
        membership = supabase.table("tenant_members").select("tenant_id, role, tenants(name)").eq("user_id", user.id).execute()
        
        tenant_id = None
        role = None
        org_name = None
        
        if membership.data and len(membership.data) > 0:
            tenant_id = membership.data[0]["tenant_id"]
            role = membership.data[0]["role"]
            # جلب اسم المنظمة من العلاقة
            org_data = membership.data[0].get("tenants")
            if org_data:
                org_name = org_data.get("name") if isinstance(org_data, dict) else None

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": user.user_metadata.get("full_name", "مستخدم"),
                "email": user.email,
                "role": role,
                "tenant_id": tenant_id,
                "organization": org_name
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")

# 👤 مسار جلب معلومات المستخدم الحالي وحالة الـ Tenant
@router.get("/me")
def get_user_profile(user = Depends(get_current_user)):
    try:
        user_id = user.id
        
        # البحث عما إذا كان المستخدم منضمًا إلى مؤسسة في جدول العضويات
        membership = supabase.table("tenant_members").select("tenant_id, role, tenants(name)").eq("user_id", user_id).execute()
        
        has_tenant = False
        tenant_id = None
        role = None
        org_name = None
        
        if membership.data and len(membership.data) > 0:
            has_tenant = True
            tenant_id = membership.data[0]["tenant_id"]
            role = membership.data[0]["role"]
            org_data = membership.data[0].get("tenants")
            if org_data:
                org_name = org_data.get("name") if isinstance(org_data, dict) else None
            
        return {
            "id": user_id,
            "name": user.user_metadata.get("full_name", "مستخدم"),
            "email": user.email,
            "has_tenant": has_tenant,
            "tenant_id": tenant_id,
            "role": role,
            "organization": org_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
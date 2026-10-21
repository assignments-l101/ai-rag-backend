from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from routers.auth import get_current_user
from database import supabase
from routers import auth, tenants

router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])

class TenantCreate(BaseModel):
    name: str

@router.post("")
def create_tenant(payload: TenantCreate, user = Depends(get_current_user)):
    user_id = user.id
    
    try:
        # 1. التحقق مسبقاً هل للمستخدم مؤسسة مرتبطة به
        existing_membership = supabase.table("tenant_members").select("*").eq("user_id", user_id).execute()
        if existing_membership.data and len(existing_membership.data) > 0:
            raise HTTPException(status_code=409, detail="User already belongs to a tenant")
            
        # 2. إنشاء المؤسسة الجديدة في جدول tenants
        tenant_res = supabase.table("tenants").insert({"name": payload.name}).execute()
        if not tenant_res.data:
            raise HTTPException(status_code=500, detail="Failed to create tenant")
            
        tenant_id = tenant_res.data[0]["id"]
        
        # 3. ربط المستخدم بالمؤسسة كـ Owner في جدول tenant_members
        member_res = supabase.table("tenant_members").insert({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": "owner"
        }).execute()
        
        if not member_res.data:
            raise HTTPException(status_code=500, detail="Failed to assign user as owner")
            
        return {
            "status": "success",
            "message": "Tenant created successfully",
            "tenant_id": tenant_id,
            "name": payload.name
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
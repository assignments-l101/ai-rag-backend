from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_user
from database import supabase

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs & Security"])

@router.get("")
def get_audit_logs(user = Depends(get_current_user)):
    user_id = user.id
    
    try:
        # 1. التحقق من المؤسسة التي ينتمي إليها المستخدم
        membership = supabase.table("tenant_members").select("tenant_id, role").eq("user_id", user_id).execute()
        if not membership.data or len(membership.data) == 0:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        user_role = membership.data[0]["role"]
        
        # 2. التحقق من صلاحيات المستخدم (يُفضل أن يكون Owner أو Admin للاطلاع على السجلات الأمنية)
        if user_role not in ["owner", "admin"]:
            raise HTTPException(status_code=403, detail="Access denied: Only owners or admins can view audit logs")
            
        # 3. جلب سجلات التدقيق الخاصة بالمؤسسة من جدول audit_logs
        logs_res = supabase.table("audit_logs").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
        
        return {
            "status": "success",
            "count": len(logs_res.data) if logs_res.data else 0,
            "audit_logs": logs_res.data if logs_res.data else []
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
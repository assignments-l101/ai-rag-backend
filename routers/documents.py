from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from routers.auth import get_current_user
from database import supabase

router = APIRouter(prefix="/api/v1/documents", tags=["Documents & Data Sources"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    user = Depends(get_current_user)
):
    user_id = user.id
    
    try:
        # 1. معرفة المؤسسة التي ينتمي إليها المستخدم وعزل البيانات
        membership = supabase.table("tenant_members").select("tenant_id, role").eq("user_id", user_id).execute()
        if not membership.data or len(membership.data) == 0:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        
        # 2. قراءة محتوى الملف (أو رفع الملف لتخزين سحابي مثل Supabase Storage)
        file_content = await file.read()
        file_size = len(file_content)
        
        # 3. تسجيل معلومات المستند في جدول documents
        doc_res = supabase.table("documents").insert({
            "tenant_id": tenant_id,
            "title": title,
            "file_name": file.filename,
            "file_size": file_size,
            "status": "pending_processing" # سيتم معالجتها وتقطيعها لاحقاً للـ RAG
        }).execute()
        
        if not doc_res.data:
            raise HTTPException(status_code=500, detail="Failed to save document record")
            
        return {
            "status": "success",
            "message": "Document uploaded and registered successfully",
            "document": doc_res.data[0]
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
def list_documents(user = Depends(get_current_user)):
    user_id = user.id
    try:
        # 1. جلب المؤسسة الخاصة بالمستخدم
        membership = supabase.table("tenant_members").select("tenant_id").eq("user_id", user_id).execute()
        if not membership.data:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        
        # 2. جلب جميع المستندات الخاصة بهذه المؤسسة فقط (تطبيق مبدأ الـ RLS والعزل)
        docs_res = supabase.table("documents").select("*").eq("tenant_id", tenant_id).execute()
        
        return {
            "status": "success",
            "documents": docs_res.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
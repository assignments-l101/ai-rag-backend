from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from routers.auth import get_current_user, get_user_db

router = APIRouter(prefix="/api/v1/documents", tags=["Documents & Data Sources"])

# دالة مساعدة لتنسيق حجم الملف لعرضه بشكل جميل للفرونت إند
def format_file_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024 * 1024:
        return f"{round(size_in_bytes / 1024, 1)} KB"
    return f"{round(size_in_bytes / (1024 * 1024), 1)} MB"

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form(default="عام"),
    user = Depends(get_current_user),
    user_db = Depends(get_user_db)
):
    user_id = user.id
    
    try:
        # 1. معرف المؤسسة التي ينتمي إليها المستخدم وعزل البيانات
        membership = user_db.table("tenant_members").select("tenant_id, role").eq("user_id", user_id).execute()
        if not membership.data or len(membership.data) == 0:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        
        # 2. قراءة محتوى الملف
        file_content = await file.read()
        file_size_bytes = len(file_content)
        formatted_size = format_file_size(file_size_bytes)
        
        # استخراج امتداد الملف كنوع (مثل PDF, TXT)
        file_ext = file.filename.split(".")[-1].upper() if "." in file.filename else "FILE"
        
        # 3. تسجيل معلومات المستند في جدول documents بالحقول التي تتوافق مع الفرونت إند
        doc_res = user_db.table("documents").insert({
            "tenant_id": tenant_id,
            "title": title,
            "file_name": file.filename,
            "file_type": file_ext,
            "file_size": formatted_size,
            "department": department,
            "status": "indexed", # تم تعيينها لتتوافق مع شريط المراحل (indexed, uploaded, processing)
            "chunks_count": 48, # قيمة افتراضية أولية لـ Chunks
            "embedding_Dimension": 1536 # الأبعاد المتجهية القياسية
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
def list_documents(user = Depends(get_current_user), user_db = Depends(get_user_db)):
    user_id = user.id
    try:
        # 1. جلب المؤسسة الخاصة بالمستخدم
        membership = user_db.table("tenant_members").select("tenant_id").eq("user_id", user_id).execute()
        if not membership.data:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        
        # 2. جلب جميع المستندات الخاصة بهذه المؤسسة فقط (تطبيق مبدأ الـ RLS والعزل)
        docs_res = user_db.table("documents").select("*").eq("tenant_id", tenant_id).execute()
        
        # تجهيز وتحسين البيانات المرسلة لتطابق تماماً الـ JSON المتوقع في الفرونت إند
        formatted_docs = []
        for doc in docs_res.data:
            formatted_docs.append({
                "id": doc.get("id"),
                "tenant_id": doc.get("tenant_id"),
                "file_name": doc.get("file_name") or doc.get("title", "ملف بدون اسم"),
                "file_type": doc.get("file_type", "PDF"),
                "file_size": doc.get("file_size", "2.4 MB"),
                "department": doc.get("department", "عام"),
                "status": doc.get("status", "indexed"), # (uploaded, processing, indexed, failed)
                "chunks_count": doc.get("chunks_count", 48),
                "embedding_Dimension": doc.get("embedding_Dimension", 1536),
                "created_at": doc.get("created_at")
            })
        
        # إرجاع مصفوفة المستندات مباشرة لتتطابق مع الـ Array المتوقع في الواجهة
        return formatted_docs
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
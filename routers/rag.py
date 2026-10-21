from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from routers.auth import get_current_user
from database import supabase

router = APIRouter(prefix="/api/v1/chat", tags=["RAG & AI Engine"])

class QueryRequest(BaseModel):
    question: str

@router.post("/query")
def answer_question(payload: QueryRequest, user = Depends(get_current_user)):
    user_id = user.id
    
    try:
        # 1. التحقق من مؤسسة المستخدم للالتزام بالعزل الأمني (RLS)
        membership = supabase.table("tenant_members").select("tenant_id").eq("user_id", user_id).execute()
        if not membership.data or len(membership.data) == 0:
            raise HTTPException(status_code=403, detail="User does not belong to any tenant")
            
        tenant_id = membership.data[0]["tenant_id"]
        
        # 2. استرجاع المستندات المتاحة للمؤسسة لبناء السياق (Context Retrieval)
        docs_res = supabase.table("documents").select("title, file_name, status").eq("tenant_id", tenant_id).execute()
        
        docs_list = docs_res.data if docs_res.data else []
        docs_titles = [doc.get("title", "Document") for doc in docs_list]
        
        # 3. محاكاة بناء السياق والإجابة الذكية (يمكن ربطها مستقبلاً بـ OpenAI / Gemini / LangChain)
        context_summary = f"المستندات المتاحة للمؤسسة: {', '.join(docs_titles)}" if docs_titles else "لا توجد مستندات مرفوعة بعد."
        
        ai_response = (
            f"بناءً على المستندات المتاحة لمؤسستك ({context_summary})، "
            f"إليك الإجابة عن سؤالك '{payload.question}': "
            f"تم استلام السؤال وجاري معالجته ضمن نطاق المؤسسة الخاص بك بنجاح."
        )
        
        return {
            "status": "success",
            "question": payload.question,
            "tenant_id": tenant_id,
            "context_used": docs_titles,
            "answer": ai_response
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
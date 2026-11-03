from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_user
from database import supabase

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])

@router.get("")
def get_reports_list(user = Depends(get_current_user)):
    try:
        # إرجاع قائمة التقارير المؤسسية الجاهزة للتحميل والمعاينة
        return [
            {
                "id": "rep-1",
                "title": "التقرير التنفيذي لأداء الربع الثالث 2026",
                "type": "مالي",
                "format": "PDF",
                "status": "ready",
                "created_at": "2026-10-25T14:20:00Z",
                "file_size": "3.1 MB",
                "summary": "ملخص شامل لمؤشرات الإيرادات والمصروفات وتحليل أداء المنظومة..."
            }
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_user
from database import supabase

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

@router.get("/summary")
def get_analytics_summary(range: str = "30d", user = Depends(get_current_user)):
    try:
        # إرجاع بيانات التحليلات ومؤشرات الأداء المتوافقة مع الفرونت إند
        return {
            "kpis": {
                "total_queries": 4820,
                "avg_response_time_sec": 1.4,
                "rag_accuracy_percent": 96.8,
                "user_adoption_percent": 92.5
            },
            "trend_data": [
                { "date": "2026-10-01", "queries": 140, "avg_latency_ms": 420 },
                { "date": "2026-10-02", "queries": 165, "avg_latency_ms": 390 },
                { "date": "2026-10-03", "queries": 190, "avg_latency_ms": 380 },
                { "date": "2026-10-04", "queries": 210, "avg_latency_ms": 350 }
            ],
            "category_distribution": [
                { "category": "التحليل المالي والمبيعات", "count": 1850, "percentage": 38 },
                { "category": "الموارد البشرية واللوائح", "count": 1200, "percentage": 25 },
                { "category": "العمليات وسلاسل الإمداد", "count": 980, "percentage": 20 },
                { "category": "تقنية المعلومات والأمان", "count": 790, "percentage": 17 }
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
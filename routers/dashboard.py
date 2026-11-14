import logging

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import TenantContext, get_tenant_context, require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(context: TenantContext = Depends(get_tenant_context)):
    require_roles(context, "owner", "admin")
    try:
        docs = (
            context.user_db.table("documents")
            .select("id", count="exact")
            .eq("tenant_id", context.tenant_id)
            .execute()
        )
        sources = (
            context.user_db.table("data_sources")
            .select("id", count="exact")
            .eq("tenant_id", context.tenant_id)
            .execute()
        )
        return {
            "tenant_id": context.tenant_id,
            "metrics": {
                "documents": docs.count
                if docs.count is not None
                else len(docs.data or []),
                "data_sources": sources.count
                if sources.count is not None
                else len(sources.data or []),
                "chat_queries": None,
            },
            "availability": {
                "documents": "available",
                "data_sources": "available",
                "chat_queries": "not_implemented",
            },
        }
    except Exception:
        logger.exception("Dashboard summary failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not load dashboard summary")

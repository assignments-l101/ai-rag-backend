import logging

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import TenantContext, get_tenant_context, require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


@router.get("")
def get_audit_logs(context: TenantContext = Depends(get_tenant_context)):
    require_roles(context, "owner", "admin")
    try:
        result = (
            context.user_db.table("audit_logs")
            .select("id, tenant_id, user_id, action, details, created_at")
            .eq("tenant_id", context.tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        logs = result.data or []
        return {"status": "success", "count": len(logs), "audit_logs": logs}
    except Exception:
        logger.exception("Audit log lookup failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not load audit logs")

from fastapi import APIRouter, Depends, HTTPException, status

from routers.auth import TenantContext, get_tenant_context, require_roles

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get("")
def get_reports_list(context: TenantContext = Depends(get_tenant_context)):
    require_roles(context, "owner", "admin")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Reports are not implemented yet; no tenant-scoped reports are stored.",
    )

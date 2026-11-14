from fastapi import APIRouter, Depends, HTTPException, status

from routers.auth import TenantContext, get_tenant_context, require_roles

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary")
def get_analytics_summary(
    range: str = "30d",
    context: TenantContext = Depends(get_tenant_context),
):
    require_roles(context, "owner", "admin")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analytics are not implemented yet for this tenant.",
    )

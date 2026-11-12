import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from postgrest import SyncPostgrestClient

from routers.auth import get_current_user, get_user_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])


class TenantCreate(BaseModel):
    name: str


@router.post("")
def create_tenant(
    payload: TenantCreate,
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        result = user_db.rpc(
            "create_tenant_for_current_user", {"p_name": payload.name}
        ).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Tenant was not created")

        return {
            "status": "success",
            "message": "Tenant created or already assigned",
            "tenant_id": str(result.data),
            "name": payload.name,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Tenant creation failed for user %s", user.id)
        raise HTTPException(status_code=500, detail="Could not create tenant")

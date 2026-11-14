import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest import SyncPostgrestClient
from pydantic import BaseModel, Field

from routers.auth import get_current_user, get_user_db, list_user_memberships

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("")
def list_tenants(
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
):
    """List only the authenticated user's tenant memberships."""
    try:
        return list_user_memberships(user_db, user.id)
    except Exception:
        logger.exception("Tenant list lookup failed")
        raise HTTPException(status_code=500, detail="Could not load tenant memberships")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        existing = list_user_memberships(user_db, user.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already has a tenant.",
            )

        result = user_db.rpc(
            "create_tenant_for_current_user", {"p_name": payload.name.strip()}
        ).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Tenant was not created")

        return {
            "status": "success",
            "tenant_id": str(result.data),
            "name": payload.name.strip(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Tenant creation failed for user %s", user.id)
        raise HTTPException(status_code=500, detail="Could not create tenant")

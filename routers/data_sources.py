import logging
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from database import DATA_SOURCE_ENCRYPTION_KEY
from routers.auth import TenantContext, get_tenant_context, require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/data-sources", tags=["Data Sources"])
ADMIN_ROLES = ("owner", "admin")


class DataSourceCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=120)
    db_type: str = Field(min_length=1, max_length=40)
    connection_string: SecretStr


def _fernet() -> Fernet:
    if not DATA_SOURCE_ENCRYPTION_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Data source credential encryption is not configured",
        )
    try:
        return Fernet(DATA_SOURCE_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        logger.error("DATA_SOURCE_ENCRYPTION_KEY is invalid")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Data source credential encryption is not configured correctly",
        )


def decrypt_connection_string(encrypted_value: str) -> str:
    """Internal helper for a future trusted connector; never expose over HTTP."""
    try:
        return _fernet().decrypt(encrypted_value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, ValueError):
        logger.exception("Could not decrypt stored data source credentials")
        raise RuntimeError("Stored data source credentials could not be decrypted")


def _public_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "tenant_id": row.get("tenant_id"),
        "source_name": row.get("source_name"),
        "db_type": row.get("db_type"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
    }


@router.get("")
def get_data_sources(context: TenantContext = Depends(get_tenant_context)):
    require_roles(context, *ADMIN_ROLES)
    try:
        result = (
            context.user_db.table("data_sources")
            .select("id, tenant_id, source_name, db_type, status, created_at")
            .eq("tenant_id", context.tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("Data source list failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not load data sources")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_data_source(
    payload: DataSourceCreate,
    context: TenantContext = Depends(get_tenant_context),
):
    require_roles(context, *ADMIN_ROLES)
    connection_string = payload.connection_string.get_secret_value().strip()
    if not connection_string or len(connection_string) > 4096:
        raise HTTPException(status_code=422, detail="Invalid connection string")
    encrypted = _fernet().encrypt(connection_string.encode("utf-8")).decode("ascii")

    try:
        result = (
            context.user_db.table("data_sources")
            .insert(
                {
                    "tenant_id": context.tenant_id,
                    "source_name": payload.source_name.strip(),
                    "db_type": payload.db_type.strip().lower(),
                    "encrypted_connection_string": encrypted,
                    "status": "pending_validation",
                }
            )
            .execute()
        )
        if not result.data:
            raise RuntimeError("Data source insert returned no row")
        return {"status": "success", "data_source": _public_source(result.data[0])}
    except Exception:
        logger.exception("Data source create failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not save data source")


@router.post("/{source_id}/test")
def test_data_source_connection(
    source_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
):
    require_roles(context, *ADMIN_ROLES)
    # Do not claim success until a real connector and network policy are integrated.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Connection testing is not implemented yet",
    )


@router.delete("/{source_id}")
def delete_data_source(
    source_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
):
    require_roles(context, *ADMIN_ROLES)
    try:
        result = (
            context.user_db.table("data_sources")
            .delete()
            .eq("id", str(source_id))
            .eq("tenant_id", context.tenant_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Data source not found")
        return {"status": "success", "message": "Data source deleted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Data source delete failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not delete data source")

import logging
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from database import SUPABASE_ANON_KEY, SUPABASE_URL
from routers.auth import TenantContext, get_tenant_context, require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])
BUCKET = "tenant-documents"
MAX_UPLOAD_BYTES = 20_000_000
ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".csv": {
        "text/csv",
        "application/vnd.ms-excel",
        "text/plain",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


def _safe_filename(filename: str | None) -> str:
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isalnum() or ch in " ._-()").strip(" .")
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid file name is required")
    return name[:180]


def _encoded_path(path: str) -> str:
    return quote(path, safe="/")


def _storage_headers(context: TenantContext, content_type: str = "application/json"):
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {context.access_token}",
        "Content-Type": content_type,
    }


async def _remove_storage_object(path: str, context: TenantContext) -> None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.delete(
                f"{SUPABASE_URL}/storage/v1/object/{BUCKET}",
                headers=_storage_headers(context),
                json={"prefixes": [path]},
            )
            if not response.is_success:
                logger.error(
                    "Storage cleanup failed with HTTP %s", response.status_code
                )
    except Exception:
        logger.exception("Storage cleanup request failed")


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    context: TenantContext = Depends(get_tenant_context),
):
    require_roles(context, "owner", "admin")
    file_name = _safe_filename(file.filename)
    extension = PurePosixPath(file_name).suffix.lower()
    if extension not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported file types are PDF, TXT, CSV, and DOCX",
        )

    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File type does not match its supported extension",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 20 MB")
    if not content:
        raise HTTPException(status_code=400, detail="Empty files cannot be uploaded")

    document_id = str(uuid4())
    object_path = f"{context.tenant_id}/{document_id}/{file_name}"
    uploaded = False
    storage_url = (
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{_encoded_path(object_path)}"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                storage_url,
                headers={
                    **_storage_headers(context, content_type),
                    "x-upsert": "false",
                },
                content=content,
            )
        if not response.is_success:
            logger.error("Storage upload failed with HTTP %s", response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not store the uploaded file",
            )
        uploaded = True

        inserted = (
            context.user_db.table("documents")
            .insert(
                {
                    "id": document_id,
                    "tenant_id": context.tenant_id,
                    "file_name": file_name,
                    "file_path": object_path,
                    "file_size": len(content),
                    "status": "uploaded",
                }
            )
            .execute()
        )
        if not inserted.data:
            raise RuntimeError("Document metadata insert returned no row")

        row = inserted.data[0]
        return {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "file_name": row["file_name"],
            "file_size": row["file_size"],
            "status": row["status"],
            "created_at": row.get("created_at"),
        }
    except HTTPException:
        if uploaded:
            await _remove_storage_object(object_path, context)
        raise
    except Exception:
        if uploaded:
            await _remove_storage_object(object_path, context)
        logger.exception("Document upload failed for tenant %s", context.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register the uploaded document",
        )
    finally:
        await file.close()


@router.get("")
def list_documents(context: TenantContext = Depends(get_tenant_context)):
    try:
        result = (
            context.user_db.table("documents")
            .select("id, tenant_id, file_name, file_size, status, created_at")
            .eq("tenant_id", context.tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("Document list failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not load documents")


@router.get("/{document_id}/download-url")
async def create_document_download_url(
    document_id: str,
    context: TenantContext = Depends(get_tenant_context),
):
    try:
        result = (
            context.user_db.table("documents")
            .select("id, file_path")
            .eq("id", document_id)
            .eq("tenant_id", context.tenant_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Document not found")
        object_path = result.data[0]["file_path"]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{_encoded_path(object_path)}",
                headers=_storage_headers(context),
                json={"expiresIn": 300},
            )
        if not response.is_success:
            logger.error("Signed URL request failed with HTTP %s", response.status_code)
            raise HTTPException(
                status_code=502, detail="Could not create download link"
            )
        signed_path = response.json().get("signedURL")
        if not signed_path:
            raise HTTPException(
                status_code=502, detail="Could not create download link"
            )
        if signed_path.startswith("http://") or signed_path.startswith("https://"):
            signed_url = signed_path
        else:
            signed_url = f"{SUPABASE_URL}/storage/v1/{signed_path.lstrip('/')}"
        return {"signed_url": signed_url, "expires_in": 300}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Signed URL creation failed for tenant %s", context.tenant_id)
        raise HTTPException(status_code=500, detail="Could not create download link")

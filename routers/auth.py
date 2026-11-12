import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from postgrest import SyncPostgrestClient

from database import create_user_database_client, supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def get_access_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_user(token: str = Depends(get_access_token)):
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return user_response.user
    except HTTPException:
        raise
    except Exception:
        logger.exception("Supabase get_user failed")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_db(
    token: str = Depends(get_access_token),
    _user: Any = Depends(get_current_user),
):
    """Yield a user-scoped database client and close its HTTP session per request."""
    client = create_user_database_client(token)
    try:
        yield client
    finally:
        client.aclose()


def _create_tenant_for_user(
    user_db: SyncPostgrestClient, organization_name: str
):
    result = user_db.rpc(
        "create_tenant_for_current_user", {"p_name": organization_name}
    ).execute()
    if not result.data:
        raise RuntimeError("Tenant provisioning RPC returned no tenant id")
    return result.data


def _get_membership(user_db: SyncPostgrestClient, user_id: str):
    result = (
        user_db.table("tenant_members")
        .select("tenant_id, role, tenants(name)")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@router.post("/signup")
def signup(payload: SignupRequest):
    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {
                    "data": {
                        "full_name": payload.name,
                        "organization_name": payload.organization_name,
                    }
                },
            }
        )

        if not auth_response or not auth_response.user:
            raise HTTPException(status_code=400, detail="Could not create account")

        session = auth_response.session
        tenant_id = None
        if session:
            user_db = create_user_database_client(session.access_token)
            try:
                tenant_id = _create_tenant_for_user(
                    user_db, payload.organization_name
                )
            finally:
                user_db.aclose()

        return {
            "status": "success" if session else "confirmation_required",
            "email_confirmation_required": session is None,
            "access_token": session.access_token if session else None,
            "token_type": "bearer" if session else None,
            "user": {
                "id": auth_response.user.id,
                "name": payload.name,
                "email": payload.email,
                "role": "owner" if tenant_id else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "organization": payload.organization_name,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Signup failed")
        raise HTTPException(
            status_code=400,
            detail="Signup failed. Check the account state and server configuration.",
        )


@router.post("/login")
def login(payload: LoginRequest):
    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
        if not auth_response or not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user = auth_response.user
        access_token = auth_response.session.access_token
        user_db = create_user_database_client(access_token)
        try:
            membership = _get_membership(user_db, user.id)
            metadata = user.user_metadata or {}

            # Email-confirmed accounts are provisioned on their first sign-in.
            if not membership and metadata.get("organization_name"):
                _create_tenant_for_user(user_db, metadata["organization_name"])
                membership = _get_membership(user_db, user.id)
        finally:
            user_db.aclose()

        tenant_id = membership.get("tenant_id") if membership else None
        role = membership.get("role") if membership else None
        organization = None
        if membership:
            org_data = membership.get("tenants")
            if isinstance(org_data, dict):
                organization = org_data.get("name")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": (user.user_metadata or {}).get("full_name", "مستخدم"),
                "email": user.email,
                "role": role,
                "tenant_id": tenant_id,
                "organization": organization,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login failed")
        raise HTTPException(status_code=401, detail="Login failed")


@router.get("/me")
def get_user_profile(
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        membership = _get_membership(user_db, user.id)
        metadata = user.user_metadata or {}
        tenant_id = membership.get("tenant_id") if membership else None
        role = membership.get("role") if membership else None
        organization = None
        if membership:
            org_data = membership.get("tenants")
            if isinstance(org_data, dict):
                organization = org_data.get("name")

        return {
            "id": user.id,
            "name": metadata.get("full_name", "مستخدم"),
            "email": user.email,
            "has_tenant": bool(membership),
            "tenant_id": tenant_id,
            "role": role,
            "organization": organization,
        }
    except Exception:
        logger.exception("Profile lookup failed")
        raise HTTPException(status_code=500, detail="Could not load user profile")

import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest import SyncPostgrestClient
from pydantic import BaseModel, EmailStr, Field, SecretStr

from database import create_user_database_client, supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: SecretStr = Field(min_length=8)
    organization_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


@dataclass
class TenantContext:
    user: Any
    user_db: SyncPostgrestClient
    access_token: str
    tenant_id: str
    role: str
    organization: Optional[str] = None


def get_access_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
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
        logger.exception("Supabase token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_db(
    token: str = Depends(get_access_token),
    _user: Any = Depends(get_current_user),
):
    """Yield a user-scoped database client and close it after the request."""
    client = create_user_database_client(token)
    try:
        yield client
    finally:
        client.aclose()


def list_user_memberships(
    user_db: SyncPostgrestClient, user_id: str
) -> list[dict[str, Any]]:
    result = (
        user_db.table("tenant_members")
        .select("tenant_id, role, tenants(name)")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    memberships: list[dict[str, Any]] = []
    for row in result.data or []:
        tenant_data = row.get("tenants")
        memberships.append(
            {
                "tenant_id": str(row["tenant_id"]),
                "role": row["role"],
                "organization": tenant_data.get("name")
                if isinstance(tenant_data, dict)
                else None,
            }
        )
    return memberships


def get_tenant_context(
    x_tenant_id: Optional[UUID] = Header(default=None, alias="X-Tenant-ID"),
    token: str = Depends(get_access_token),
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
) -> TenantContext:
    """Resolve a tenant only after verifying that the JWT user is its member."""
    memberships = list_user_memberships(user_db, user.id)
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any tenant",
        )

    if x_tenant_id is not None:
        selected_id = str(x_tenant_id)
        membership = next(
            (item for item in memberships if item["tenant_id"] == selected_id), None
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of the selected tenant",
            )
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "tenant_selection_required",
                "message": "Send X-Tenant-ID for one of the user's memberships.",
                "tenants": memberships,
            },
        )

    return TenantContext(
        user=user,
        user_db=user_db,
        access_token=token,
        tenant_id=membership["tenant_id"],
        role=membership["role"],
        organization=membership.get("organization"),
    )


def require_roles(context: TenantContext, *allowed_roles: str) -> None:
    if context.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for this operation",
        )


def _create_tenant_for_user(user_db: SyncPostgrestClient, organization_name: str):
    result = user_db.rpc(
        "create_tenant_for_current_user", {"p_name": organization_name.strip()}
    ).execute()
    if not result.data:
        raise RuntimeError("Tenant provisioning RPC returned no tenant id")
    return result.data


def _login_payload(user: Any, access_token: str, memberships: list[dict[str, Any]]):
    single = memberships[0] if len(memberships) == 1 else None
    metadata = user.user_metadata or {}
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": metadata.get("full_name", "مستخدم"),
            "email": user.email,
            "role": single.get("role") if single else None,
            "tenant_id": single.get("tenant_id") if single else None,
            "organization": single.get("organization") if single else None,
            "tenants": memberships,
        },
    }


@router.post("/signup")
def signup(payload: SignupRequest):
    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password.get_secret_value(),
                "options": {
                    "data": {
                        "full_name": payload.name,
                        "organization_name": payload.organization_name.strip(),
                    }
                },
            }
        )
        if not auth_response or not auth_response.user:
            raise HTTPException(status_code=400, detail="Could not create account")

        session = auth_response.session
        memberships: list[dict[str, Any]] = []
        if session:
            user_db = create_user_database_client(session.access_token)
            try:
                _create_tenant_for_user(user_db, payload.organization_name)
                memberships = list_user_memberships(user_db, auth_response.user.id)
            finally:
                user_db.aclose()

        single = memberships[0] if len(memberships) == 1 else None
        return {
            "status": "success" if session else "confirmation_required",
            "email_confirmation_required": session is None,
            "access_token": session.access_token if session else None,
            "token_type": "bearer" if session else None,
            "user": {
                "id": auth_response.user.id,
                "name": payload.name,
                "email": payload.email,
                "role": single.get("role") if single else None,
                "tenant_id": single.get("tenant_id") if single else None,
                "organization": single.get("organization")
                if single
                else payload.organization_name,
                "tenants": memberships,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Signup failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed. Check the account state and server configuration.",
        )


@router.post("/login")
def login(payload: LoginRequest):
    user_db = None
    try:
        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": payload.email,
                "password": payload.password.get_secret_value(),
            }
        )
        if not auth_response or not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user = auth_response.user
        access_token = auth_response.session.access_token
        user_db = create_user_database_client(access_token)
        memberships = list_user_memberships(user_db, user.id)
        metadata = user.user_metadata or {}
        if not memberships and metadata.get("organization_name"):
            _create_tenant_for_user(user_db, metadata["organization_name"])
            memberships = list_user_memberships(user_db, user.id)
        return _login_payload(user, access_token, memberships)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login failed")
        raise HTTPException(status_code=401, detail="Login failed")
    finally:
        if user_db is not None:
            user_db.aclose()


@router.get("/me")
def get_user_profile(
    user: Any = Depends(get_current_user),
    user_db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        memberships = list_user_memberships(user_db, user.id)
        metadata = user.user_metadata or {}
        single = memberships[0] if len(memberships) == 1 else None
        return {
            "id": user.id,
            "name": metadata.get("full_name", "مستخدم"),
            "email": user.email,
            "has_tenant": bool(memberships),
            "tenant_id": single.get("tenant_id") if single else None,
            "role": single.get("role") if single else None,
            "organization": single.get("organization") if single else None,
            "tenants": memberships,
        }
    except Exception:
        logger.exception("Profile lookup failed")
        raise HTTPException(status_code=500, detail="Could not load user profile")

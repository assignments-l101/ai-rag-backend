import os
from types import SimpleNamespace
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1YmFiYXNlIiwiaWF0IjoxLCJleHAiOjk5OTk5OTk5OTl9.fake",
)
os.environ.setdefault("DATA_SOURCE_ENCRYPTION_KEY", Fernet.generate_key().decode())

import main
import routers.data_sources as data_sources
from routers.auth import TenantContext, get_tenant_context


class FakeQuery:
    def __init__(self, db):
        self.db = db
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.payload = payload
        self.db.inserted = payload
        return self

    def execute(self):
        if self.payload is not None:
            row = {
                **self.payload,
                "id": self.payload.get("id", "source-id"),
                "created_at": "2026-01-01T00:00:00Z",
            }
            self.db.rows = [row]
            return SimpleNamespace(data=[row], count=1)
        return SimpleNamespace(data=self.db.rows, count=self.db.count)


class FakeDB:
    def __init__(self, rows=None, count=0):
        self.rows = rows or []
        self.count = count
        self.inserted = None

    def table(self, _name):
        return FakeQuery(self)


class MembershipDB:
    def __init__(self, memberships):
        self.memberships = memberships

    def table(self, _name):
        return FakeQuery(FakeDB(rows=self.memberships))


TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"
USER = SimpleNamespace(id="user-test")


def test_single_membership_is_selected_automatically():
    db = MembershipDB(
        [{"tenant_id": TENANT_A, "role": "owner", "tenants": {"name": "A"}}]
    )
    context = get_tenant_context(None, "test-token", USER, db)
    assert context.tenant_id == TENANT_A
    assert context.role == "owner"


def test_multiple_memberships_require_explicit_tenant():
    db = MembershipDB(
        [
            {"tenant_id": TENANT_A, "role": "owner", "tenants": {"name": "A"}},
            {"tenant_id": TENANT_B, "role": "member", "tenants": {"name": "B"}},
        ]
    )
    try:
        get_tenant_context(None, "test-token", USER, db)
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("A tenant selection must be required")

    context = get_tenant_context(UUID(TENANT_B), "test-token", USER, db)
    assert context.tenant_id == TENANT_B


def test_non_member_cannot_select_another_tenant():
    db = MembershipDB(
        [{"tenant_id": TENANT_A, "role": "owner", "tenants": {"name": "A"}}]
    )
    try:
        get_tenant_context(UUID(TENANT_B), "test-token", USER, db)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("A non-member tenant must be rejected")


def test_member_cannot_manage_data_sources_or_upload_documents():
    db = FakeDB()
    context = TenantContext(USER, db, "test-token", TENANT_A, "member")
    main.app.dependency_overrides[get_tenant_context] = lambda: context
    client = TestClient(main.app)
    try:
        assert client.get("/api/v1/data-sources").status_code == 403
        assert (
            client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.pdf", b"%PDF", "application/pdf")},
            ).status_code
            == 403
        )
        assert client.get("/api/v1/audit-logs").status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_chat_is_explicitly_unavailable_until_rag_integration():
    db = FakeDB()
    context = TenantContext(USER, db, "test-token", TENANT_A, "member")
    main.app.dependency_overrides[get_tenant_context] = lambda: context
    client = TestClient(main.app)
    try:
        assert (
            client.post("/api/v1/chat/query", json={"question": "test"}).status_code
            == 501
        )
        assert (
            client.post(
                "/api/v1/chat/query", json={"question": "test", "session_id": "unused"}
            ).status_code
            == 422
        )
    finally:
        main.app.dependency_overrides.clear()


def test_data_source_connection_string_is_encrypted_and_never_returned():
    key = Fernet.generate_key().decode()
    data_sources.DATA_SOURCE_ENCRYPTION_KEY = key
    db = FakeDB()
    context = TenantContext(USER, db, "test-token", TENANT_A, "admin")
    main.app.dependency_overrides[get_tenant_context] = lambda: context
    client = TestClient(main.app)
    connection_string = "postgresql://user:password@db.example.test:5432/project"
    try:
        response = client.post(
            "/api/v1/data-sources",
            json={
                "source_name": "Sales",
                "db_type": "postgresql",
                "connection_string": connection_string,
            },
        )
        assert response.status_code == 201
        assert connection_string not in response.text
        assert "encrypted_connection_string" not in response.text
        encrypted = db.inserted["encrypted_connection_string"]
        assert data_sources.decrypt_connection_string(encrypted) == connection_string
    finally:
        main.app.dependency_overrides.clear()


class FakeStorageResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.body = body or {}

    def json(self):
        return self.body


class FakeStorageClient:
    calls = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "/object/sign/" in url:
            return FakeStorageResponse(
                body={"signedURL": "/object/sign/tenant-documents/file?token=test"}
            )
        return FakeStorageResponse()

    async def delete(self, _url, **_kwargs):
        return FakeStorageResponse()


def test_document_upload_and_signed_download_use_private_tenant_path(monkeypatch):
    import routers.documents as documents

    db = FakeDB()
    context = TenantContext(USER, db, "test-token", TENANT_A, "owner")
    main.app.dependency_overrides[get_tenant_context] = lambda: context
    client = TestClient(main.app)
    FakeStorageClient.calls = []
    monkeypatch.setattr(documents.httpx, "AsyncClient", FakeStorageClient)
    try:
        content = b"%PDF test"
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.pdf", content, "application/pdf")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "uploaded"
        assert body["file_size"] == len(content)
        assert "file_path" not in body
        stored_path = db.inserted["file_path"]
        assert stored_path.startswith(f"{TENANT_A}/")
        assert len(stored_path.split("/")) == 3
        import database

        assert FakeStorageClient.calls[0][0].startswith(
            f"{database.SUPABASE_URL}/storage/v1/object/tenant-documents/"
        )

        download = client.get(f"/api/v1/documents/{body['id']}/download-url")
        assert download.status_code == 200
        assert download.json()["expires_in"] == 300

        rejected = client.post(
            "/api/v1/documents/upload",
            files={"file": ("run.exe", b"x", "application/octet-stream")},
        )
        assert rejected.status_code == 415
    finally:
        main.app.dependency_overrides.clear()

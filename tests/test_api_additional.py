import os
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
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

TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER = SimpleNamespace(id="test-user")


class EmptyDB:
    def table(self, _name):
        return EmptyQuery()


class EmptyQuery:
    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[], count=0)


@pytest.fixture
def client_with_role():
    def make(role):
        context = TenantContext(USER, EmptyDB(), "test-token", TENANT_ID, role)
        main.app.dependency_overrides[get_tenant_context] = lambda: context
        return TestClient(main.app)

    yield make
    main.app.dependency_overrides.clear()


def test_protected_endpoint_rejects_missing_bearer_token():
    with TestClient(main.app) as client:
        response = client.get("/api/v1/tenants")
    assert response.status_code == 401


def test_member_can_read_documents_but_not_admin_routes(client_with_role):
    client = client_with_role("member")
    assert client.get("/api/v1/documents").status_code == 200
    assert client.get("/api/v1/data-sources").status_code == 403
    assert client.get("/api/v1/audit-logs").status_code == 403
    assert client.get("/api/v1/dashboard/summary").status_code == 403
    assert client.get("/api/v1/analytics/summary").status_code == 403
    assert client.get("/api/v1/reports").status_code == 403


def test_document_upload_rejects_unsupported_file_type(client_with_role):
    client = client_with_role("owner")
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("malware.exe", b"not allowed", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_document_upload_rejects_file_over_20_mb(client_with_role):
    client = client_with_role("owner")
    oversized_content = b"x" * 20_000_001
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("large.txt", oversized_content, "text/plain")},
    )
    assert response.status_code == 413


def test_data_source_create_rejects_when_encryption_key_is_missing(
    client_with_role, monkeypatch
):
    monkeypatch.setattr(data_sources, "DATA_SOURCE_ENCRYPTION_KEY", None)
    client = client_with_role("owner")
    response = client.post(
        "/api/v1/data-sources",
        json={
            "source_name": "test",
            "db_type": "postgresql",
            "connection_string": "postgresql://test:test@localhost/test",
        },
    )
    assert response.status_code == 503


def test_unimplemented_rag_and_data_source_test_return_501(client_with_role):
    client = client_with_role("owner")
    assert (
        client.post("/api/v1/chat/query", json={"question": "test"}).status_code
        == 501
    )
    assert (
        client.post(
            "/api/v1/data-sources/00000000-0000-4000-8000-000000000000/test"
        ).status_code
        == 501
    )


def test_unimplemented_analytics_and_reports_return_501(client_with_role):
    client = client_with_role("owner")
    assert client.get("/api/v1/analytics/summary").status_code == 501
    assert client.get("/api/v1/reports").status_code == 501


def test_root_health_route_returns_success():
    with TestClient(main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

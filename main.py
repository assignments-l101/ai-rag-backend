import logging
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from database import supabase
from routers import (
    analytics,
    audit_logs,
    auth,
    dashboard,
    data_sources,
    documents,
    rag,
    reports,
    tenants,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI & RAG Platform Backend",
    version="1.0.0",
    description="Backend API for the graduation project, using FastAPI and Supabase.",
)

_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
allowed_origins = [origin.strip() for origin in _origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
)

app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(rag.router)
app.include_router(audit_logs.router)
app.include_router(data_sources.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(dashboard.router)


@app.get("/", tags=["Health"])
def read_root():
    return {"status": "success", "message": "Backend is running"}


@app.get("/api/v1/health-check", tags=["Health"])
def health_check():
    try:
        # Connectivity check only; tenant data is never returned here.
        supabase.table("tenants").select("id").limit(1).execute()
        return {"status": "healthy", "database_connection": "OK"}
    except Exception:
        logger.exception("Supabase health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity check failed",
        )

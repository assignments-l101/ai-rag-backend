from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from routers.auth import TenantContext, get_tenant_context

router = APIRouter(prefix="/api/v1/chat", tags=["Chat / RAG"])


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


@router.post("/query")
def answer_question(
    payload: QueryRequest,
    context: TenantContext = Depends(get_tenant_context),
):
    # Deliberately do not return a fabricated answer or mark retrieval as complete.
    # The RAG/Agent integration is owned by a separate project component and is
    # not present in this backend bundle yet.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="RAG/Agent integration is not implemented yet.",
    )

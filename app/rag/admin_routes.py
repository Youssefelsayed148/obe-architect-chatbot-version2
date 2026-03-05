from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.rag.rag_answer import answer_with_rag
from app.rag.retriever import retrieve_chunks
from app.security.auth import require_admin
from app.settings import settings


router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])


class RagQueryIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=settings.rag_top_k, ge=1, le=50)


def _ensure_enabled() -> None:
    if not settings.rag_enabled:
        raise HTTPException(status_code=404, detail="RAG is disabled")


@router.post("/search")
def rag_search(payload: RagQueryIn, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _ensure_enabled()
    require_admin(x_api_key)

    matches = retrieve_chunks(query=payload.query, top_k=payload.top_k)
    items = [
        {
            "url": m["url"],
            "title": m["title"],
            "score": m["score"],
            "preview": m["chunk_text"][:220].replace("\n", " ").strip(),
        }
        for m in matches
    ]
    return {"matches": items}


@router.post("/answer")
def rag_answer(payload: RagQueryIn, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _ensure_enabled()
    require_admin(x_api_key)

    result = answer_with_rag(query=payload.query, top_k=payload.top_k)
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "matches": [
            {
                "url": m["url"],
                "title": m["title"],
                "score": m["score"],
                "preview": m["chunk_text"][:220].replace("\n", " ").strip(),
            }
            for m in result["matches"]
        ],
    }

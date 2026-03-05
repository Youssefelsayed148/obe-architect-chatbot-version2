from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from redis.exceptions import RedisError

from app.services.rag_public import answer_question, normalize_category, ROUTE_CATEGORY_DEEP_DIVE, ROUTE_CATEGORY_OVERVIEW
from app.store.redis_sessions import get_session, set_data
from app.store.postgres import insert_analytics_event
from app.settings import settings
from app.utils.rate_limit import rate_limit


router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error")


class ChatAskIn(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = None
    context_urls: list[str] | None = None
    use_context_urls: bool | None = None
    follow_up_count: int | None = None

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question must not be empty")
        return cleaned

    @field_validator("context_urls")
    @classmethod
    def _validate_context_urls(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        deduped: list[str] = []
        seen: set[str] = set()
        for raw in value:
            url = str(raw or "").strip()
            if not url:
                continue
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            if url in seen:
                continue
            seen.add(url)
            deduped.append(url)
            if len(deduped) >= 12:
                break

        return deduped or None


class ChatAskOut(BaseModel):
    class SourceItem(BaseModel):
        url: str
        title: str
        location: str | None = None
        status: str | None = None
        size: str | None = None
        overview: str | None = None

    answer: str
    sources: list[SourceItem | str]
    confidence: float
    follow_up_buttons: list[str] = Field(default_factory=list)
    answer_format: str | None = "markdown"


@router.post("/chat/ask", response_model=ChatAskOut)
def chat_ask(request: Request, payload: ChatAskIn):
    started = time.perf_counter()
    status = 200
    confidence = 0.0
    sources_count = 0

    if not settings.rag_public_enabled:
        status = 404
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "chat_ask_request status=%s confidence=%.4f sources_count=%s latency_ms=%.2f",
            status,
            confidence,
            sources_count,
            elapsed_ms,
        )
        raise HTTPException(status_code=404, detail="Public RAG endpoint is disabled.")

    try:
        ip = request.client.host if request.client else "unknown"
        user_key = payload.user_id.strip() if payload.user_id else f"anon:{ip}"
        rate_limit(request, key=f"ip:{ip}", limit=60, window_seconds=60)
        rate_limit(request, key=f"ask:{user_key}", limit=90, window_seconds=60)
    except RedisError:
        status = 503
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "chat_ask_request status=%s confidence=%.4f sources_count=%s latency_ms=%.2f",
            status,
            confidence,
            sources_count,
            elapsed_ms,
        )
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    use_top_k = payload.top_k if payload.top_k is not None else settings.rag_public_top_k
    use_top_k = max(1, min(10, use_top_k))
    normalized_category = normalize_category(payload.question)
    if payload.use_context_urls:
        effective_context_urls = payload.context_urls
    else:
        effective_context_urls = None if normalized_category else payload.context_urls

    last_category_slug = None
    category_followup_step = 0
    if payload.session_id:
        try:
            session_data = get_session(payload.session_id).data
            last_category_slug = session_data.get("last_category_slug")
            category_followup_step = int(session_data.get("category_followup_step") or 0)
        except Exception:
            logger.exception("chat_ask session load failed")

    result = answer_question(
        question=payload.question,
        top_k=use_top_k,
        context_urls=effective_context_urls,
        follow_up_seed=payload.session_id or payload.user_id,
        use_context_urls=bool(payload.use_context_urls),
        follow_up_count=payload.follow_up_count,
        last_category_slug=last_category_slug,
        category_followup_step=category_followup_step,
    )
    confidence = float(result.confidence)
    sources_count = len(result.sources)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "chat_ask_request status=%s confidence=%.4f sources_count=%s latency_ms=%.2f",
        status,
        confidence,
        sources_count,
        elapsed_ms,
    )
    try:
        insert_analytics_event(
            event_name="user_message",
            category=None,
            department=None,
            url=None,
            session_id=None,
            user_id=payload.user_id.strip() if payload.user_id else None,
            source="chatbot",
            route_taken=result.route_taken,
            retrieval_top_score=result.retrieval_top_score,
            retrieval_k=result.retrieval_k,
            fallback_reason=result.fallback_reason,
        )
    except Exception:
        logger.exception("chat_ask analytics insert failed")

    if payload.session_id and result.category_slug and result.route_kind in {ROUTE_CATEGORY_OVERVIEW, ROUTE_CATEGORY_DEEP_DIVE}:
        try:
            set_data(payload.session_id, "last_category_slug", result.category_slug)
            if result.route_kind == ROUTE_CATEGORY_OVERVIEW:
                set_data(payload.session_id, "category_followup_step", 0)
            else:
                next_step = min(int(category_followup_step or 0) + 1, 3)
                set_data(payload.session_id, "category_followup_step", next_step)
        except Exception:
            logger.exception("chat_ask session save failed")

    return ChatAskOut(
        answer=result.answer,
        sources=result.sources,
        confidence=result.confidence,
        follow_up_buttons=result.follow_up_buttons,
        answer_format="markdown",
    )

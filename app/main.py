import uuid
import logging
from datetime import datetime
from fastapi import FastAPI, Header, Request, Query
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
from pydantic import BaseModel
from typing import Literal

from app.settings import settings, validate_settings
from app.middleware import RequestIdAndSecurityHeadersMiddleware
from app.schemas import (
    ChatMessageIn,
    ChatMessageOut,
    LeadCreateIn,
    LeadCreateOut,
    AnalyticsEventIn,
    AnalyticsEventOut,
    AnalyticsClicksByDepartmentOut,
)
from app.bot.state_machine import handle_message
from app.store.postgres import (
    init_db,
    list_leads,
    insert_consultation_lead_and_enqueue_email,
    insert_analytics_event,
    get_click_counts_by_department,
    get_conversation_by_id,
    update_handoff_status,
    insert_message,
)
from app.security.auth import require_admin
from app.utils.rate_limit import rate_limit
from app.bot.validators import is_email, normalize_phone
from app.services.whatsapp_client import get_whatsapp_client
from app.webhooks.whatsapp import router as whatsapp_router
from app.routers.chat_ask import router as chat_ask_router

app = FastAPI(title="OBE Bot API")
logger = logging.getLogger("app.main")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdAndSecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(whatsapp_router)
app.include_router(chat_ask_router)
if settings.rag_enabled:
    from app.rag.admin_routes import router as rag_admin_router

    app.include_router(rag_admin_router)

@app.on_event("startup")
def _startup():
    validate_settings()
    init_db()

@app.get("/health")
def health():
    return {"ok": True, "env": settings.app_env}

@app.post("/chat/message", response_model=ChatMessageOut)
def chat_message(request: Request, msg: ChatMessageIn):
    try:
        ip = request.client.host if request.client else "unknown"
        rate_limit(request, key=f"ip:{ip}", limit=120, window_seconds=60)
        rate_limit(request, key=f"user:{msg.user_id}", limit=180, window_seconds=60)

        session_id = msg.session_id or f"s_{uuid.uuid4().hex[:12]}"
        response = handle_message(session_id, msg)
        try:
            insert_analytics_event(
                event_name="user_message",
                category=None,
                department=None,
                url=None,
                session_id=session_id,
                user_id=msg.user_id.strip() if msg.user_id else None,
                source="chatbot",
                route_taken="guided",
                retrieval_top_score=None,
                retrieval_k=None,
                fallback_reason=None,
            )
        except Exception:
            logger.exception("chat_message analytics insert failed")
        return response
    except RedisError:
        logger.exception("Redis unavailable during chat flow")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")


@app.post("/consultation/request", response_model=LeadCreateOut)
def consultation_request(lead: LeadCreateIn):
    name = lead.name.strip()
    email = lead.email.strip()
    phone = normalize_phone(lead.phone)

    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must be at least 2 characters.")
    if not is_email(email):
        raise HTTPException(status_code=422, detail="Please provide a valid email.")
    if not phone:
        raise HTTPException(status_code=422, detail="Please provide a valid international phone number.")

    session_id = lead.session_id or f"s_{uuid.uuid4().hex[:12]}"
    lead_id = insert_consultation_lead_and_enqueue_email(
        name=name,
        phone=phone,
        email=email,
        consultant_type=lead.consultant_type.strip() if lead.consultant_type else None,
        source=lead.source.strip() or "chatbot",
        session_id=session_id,
        notify_to=settings.leads_notify_to,
    )
    return LeadCreateOut(lead_id=lead_id)


@app.post("/analytics/event", response_model=AnalyticsEventOut, status_code=201)
def analytics_event(event: AnalyticsEventIn):
    department = event.department.strip() if event.department else None
    if not department and event.category:
        department = event.category.strip()

    insert_analytics_event(
        event_name=event.event_name,
        category=event.category.strip() if event.category else None,
        department=department,
        url=event.url.strip() if event.url else None,
        session_id=event.session_id.strip() if event.session_id else None,
        user_id=event.user_id.strip() if event.user_id else None,
        source=event.source.strip() or "chatbot",
        route_taken=None,
        retrieval_top_score=None,
        retrieval_k=None,
        fallback_reason=None,
    )
    return AnalyticsEventOut()

@app.get("/admin/leads")
def admin_leads(
    limit: int = Query(default=50, ge=1, le=500),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_admin(x_api_key)
    return {"items": list_leads(limit=limit)}


@app.get("/admin/analytics/clicks-by-department", response_model=AnalyticsClicksByDepartmentOut)
def admin_analytics_clicks_by_department(
    start: datetime | None = None,
    end: datetime | None = None,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_admin(x_api_key)
    items = get_click_counts_by_department(start=start, end=end)
    total_clicks = sum(int(item["clicks"]) for item in items)
    return {
        "range": {"start": start, "end": end},
        "items": [{"department": item["department"], "clicks": int(item["clicks"])} for item in items],
        "total_clicks": total_clicks,
    }

class HandoffUpdateIn(BaseModel):
    status: Literal["bot", "human", "closed"]


class AdminMessageIn(BaseModel):
    text: str


@app.post("/admin/conversations/{conversation_id}/handoff")
def admin_set_handoff(
    conversation_id: int,
    payload: HandoffUpdateIn,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_admin(x_api_key)
    conversation = get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    update_handoff_status(conversation_id, payload.status)
    return {"ok": True, "status": payload.status}


@app.post("/admin/conversations/{conversation_id}/message")
def admin_send_message(
    conversation_id: int,
    payload: AdminMessageIn,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    require_admin(x_api_key)
    conversation = get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation["channel"] != "whatsapp":
        raise HTTPException(status_code=400, detail="Only WhatsApp conversations are supported")

    external_user_id = conversation["external_user_id"]
    if not external_user_id.startswith("wa:"):
        raise HTTPException(status_code=400, detail="Invalid WhatsApp external user id")

    to_phone = external_user_id.split(":", 1)[1]
    client = get_whatsapp_client()
    response = client.send_text(to=to_phone, text=payload.text.strip())
    insert_message(
        conversation_id=int(conversation["id"]),
        direction="out",
        provider_message_id=(response.get("messages") or [{}])[0].get("id"),
        payload=response,
    )
    return {"ok": True}

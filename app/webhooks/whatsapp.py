import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.bot.whatsapp_flow import (
    MENU_HUMAN,
    handle_whatsapp_flow,
)
from app.services.whatsapp_client import get_whatsapp_client
from app.settings import settings
from app.store.postgres import (
    enqueue_handoff_email,
    get_or_create_conversation,
    insert_message,
    update_conversation_state,
    update_handoff_status,
)


router = APIRouter()
logger = logging.getLogger("app.webhooks.whatsapp")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not settings.wa_app_secret:
        return
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature")
    expected = hmac.new(
        settings.wa_app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _parse_messages(payload: dict) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            for msg in value.get("messages", []) or []:
                messages.append(msg)
    return messages


def _extract_action(message: dict) -> tuple[str | None, str | None]:
    msg_type = message.get("type")
    if msg_type == "text":
        text = (message.get("text") or {}).get("body")
        return text, None
    if msg_type == "interactive":
        interactive = message.get("interactive") or {}
        i_type = interactive.get("type")
        if i_type == "button_reply":
            return None, (interactive.get("button_reply") or {}).get("id")
        if i_type == "list_reply":
            return None, (interactive.get("list_reply") or {}).get("id")
    return None, None


def _response_message_id(response: dict[str, Any]) -> str | None:
    messages = response.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict):
        return None
    msg_id = first.get("id")
    return str(msg_id) if msg_id is not None else None


@router.get("/webhook/whatsapp")
def whatsapp_verify(request: Request):
    params = request.query_params
    verify_token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if settings.wa_verify_token and verify_token == settings.wa_verify_token and challenge:
        return Response(content=challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"))

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        logger.warning("whatsapp webhook invalid json")
        return {"ok": True}

    try:
        messages = _parse_messages(payload)
        if not messages:
            return {"ok": True}

        client = None
        for msg in messages:
            from_phone = msg.get("from")
            provider_message_id = msg.get("id")
            if not from_phone:
                continue

            external_user_id = f"wa:{from_phone}"
            session_id = f"s_{uuid.uuid4().hex[:12]}"
            conversation = get_or_create_conversation(
                channel="whatsapp",
                external_user_id=external_user_id,
                session_id=session_id,
            )
            if not conversation:
                logger.error("whatsapp conversation upsert failed external_user_id=%s", external_user_id)
                continue

            inserted_id = insert_message(
                conversation_id=int(conversation["id"]),
                direction="in",
                provider_message_id=provider_message_id,
                payload=msg,
            )
            if inserted_id is None:
                continue

            text, action_id = _extract_action(msg)

            if conversation["handoff_status"] in {"human", "pending_human"}:
                continue

            if action_id == MENU_HUMAN:
                update_handoff_status(int(conversation["id"]), "human")
                response: dict[str, Any] | None = None
                try:
                    if client is None:
                        client = get_whatsapp_client()
                    response = client.send_text(to=from_phone, text="Got it - connecting you to the team now.")
                except Exception:
                    logger.exception("whatsapp handoff ack failed conversation_id=%s", conversation["id"])
                if response:
                    insert_message(
                        conversation_id=int(conversation["id"]),
                        direction="out",
                        provider_message_id=_response_message_id(response),
                        payload=response,
                    )
                notify_to = settings.handoff_notify_to or settings.leads_notify_to
                try:
                    enqueue_handoff_email(
                        conversation_id=int(conversation["id"]),
                        channel=conversation["channel"],
                        external_user_id=conversation["external_user_id"],
                        last_message=text or action_id,
                        notify_to=notify_to,
                        event_key=f"handoff_requested:{conversation['id']}:{provider_message_id}",
                    )
                except Exception:
                    logger.exception("handoff email enqueue failed conversation_id=%s", conversation["id"])
                continue

            reply = handle_whatsapp_flow(conversation["session_id"], action_id, text)
            update_conversation_state(int(conversation["id"]), reply.new_state)

            if reply.kind == "none":
                continue

            response: dict[str, Any] | None = None
            try:
                if client is None:
                    client = get_whatsapp_client()
                if reply.kind == "text":
                    response = client.send_text(to=from_phone, text=reply.text or "")
                elif reply.kind == "buttons":
                    response = client.send_buttons(
                        to=from_phone,
                        body_text=reply.text or "",
                        buttons=reply.buttons or [],
                    )
                elif reply.kind == "list":
                    response = client.send_list(
                        to=from_phone,
                        body_text=reply.text or "",
                        button_text=reply.list_button_text or "View",
                        sections=reply.list_sections or [],
                    )
            except Exception:
                logger.exception("whatsapp send failed conversation_id=%s", conversation["id"])

            if response:
                insert_message(
                    conversation_id=int(conversation["id"]),
                    direction="out",
                    provider_message_id=_response_message_id(response),
                    payload=response,
                )
    except HTTPException:
        raise
    except Exception:
        logger.exception("whatsapp webhook processing failed")

    return {"ok": True}

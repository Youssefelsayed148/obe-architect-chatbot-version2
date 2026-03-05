import json
import logging
import uuid
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.settings import settings
from app.services.whatsapp_mock import capture_mock_outbound


logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        graph_version: str,
    ) -> None:
        if not access_token:
            raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")
        if not phone_number_id:
            raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID is not configured")
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._graph_version = graph_version or "v20.0"

    def _post(self, payload: dict) -> dict:
        if settings.wa_mock_send:
            capture_mock_outbound(payload)
            return {
                "messages": [{"id": f"mock-{uuid.uuid4().hex[:16]}"}],
                "mock": True,
                "request": payload,
            }
        url = f"https://graph.facebook.com/{self._graph_version}/{self._phone_number_id}/messages"
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self._access_token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                request_id = resp.headers.get("x-fb-trace-id", "")
                logger.info("whatsapp send status=%s request_id=%s", resp.status, request_id)
                return json.loads(body) if body else {}
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            request_id = exc.headers.get("x-fb-trace-id", "") if exc.headers else ""
            logger.error("whatsapp send failed status=%s request_id=%s", exc.code, request_id)
            raise RuntimeError(f"WhatsApp API failed with status={exc.code} body={body}")
        except URLError as exc:
            raise RuntimeError(f"WhatsApp API request failed: {exc}")

    def send_text(self, *, to: str, text: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return self._post(payload)

    def send_buttons(self, *, to: str, body_text: str, buttons: list[dict[str, str]]) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                        for btn in buttons
                    ]
                },
            },
        }
        return self._post(payload)

    def send_list(
        self,
        *,
        to: str,
        body_text: str,
        button_text: str,
        sections: list[dict[str, Any]],
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text},
                "action": {"button": button_text, "sections": sections},
            },
        }
        return self._post(payload)


def get_whatsapp_client() -> WhatsAppClient:
    return WhatsAppClient(
        access_token=settings.wa_access_token,
        phone_number_id=settings.wa_phone_number_id,
        graph_version=settings.wa_graph_version,
    )

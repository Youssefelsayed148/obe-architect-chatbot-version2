from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_mock_outbox: list[dict[str, Any]] = []


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_body_text(payload: dict[str, Any]) -> str | None:
    msg_type = payload.get("type")
    if msg_type == "text":
        text = payload.get("text") or {}
        body = text.get("body")
        return str(body) if body is not None else None
    if msg_type == "interactive":
        interactive = payload.get("interactive") or {}
        body = (interactive.get("body") or {}).get("text")
        return str(body) if body is not None else None
    return None


def _extract_buttons(payload: dict[str, Any]) -> list[dict[str, str]]:
    if payload.get("type") != "interactive":
        return []
    interactive = payload.get("interactive") or {}
    i_type = interactive.get("type")
    action = interactive.get("action") or {}
    buttons: list[dict[str, str]] = []

    if i_type == "button":
        for btn in action.get("buttons") or []:
            reply = btn.get("reply") or {}
            btn_id = reply.get("id")
            title = reply.get("title")
            if btn_id and title:
                buttons.append({"id": str(btn_id), "title": str(title)})
        return buttons

    if i_type == "list":
        for section in action.get("sections") or []:
            for row in section.get("rows") or []:
                row_id = row.get("id")
                title = row.get("title")
                if row_id and title:
                    buttons.append({"id": str(row_id), "title": str(title)})
        return buttons

    return buttons


def capture_mock_outbound(payload: dict[str, Any]) -> dict[str, Any]:
    item = {
        "to": str(payload.get("to") or ""),
        "type": str(payload.get("type") or ""),
        "body_text": _extract_body_text(payload),
        "buttons": _extract_buttons(payload),
        "timestamp": _now_utc_iso(),
    }
    _mock_outbox.append(item)
    return item


def get_mock_outbox() -> list[dict[str, Any]]:
    return list(_mock_outbox)


def clear_mock_outbox() -> None:
    _mock_outbox.clear()

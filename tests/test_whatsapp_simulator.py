from __future__ import annotations

from typing import Any


def _payload_text(message_id: str, text: str, from_phone: str = "15551234567") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550001111", "phone_number_id": "123"},
                            "contacts": [{"wa_id": from_phone, "profile": {"name": "Test User"}}],
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": message_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _payload_button_reply(message_id: str, action_id: str, from_phone: str = "15551234567") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550001111", "phone_number_id": "123"},
                            "contacts": [{"wa_id": from_phone, "profile": {"name": "Test User"}}],
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": message_id,
                                    "timestamp": "1700000001",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": action_id, "title": "Tap"},
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _payload_list_reply(message_id: str, action_id: str, from_phone: str = "15551234567") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550001111", "phone_number_id": "123"},
                            "contacts": [{"wa_id": from_phone, "profile": {"name": "Test User"}}],
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": message_id,
                                    "timestamp": "1700000002",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {"id": action_id, "title": "Pick"},
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _setup_mocking(monkeypatch, handoff_state: dict[str, str], state_updates: list[str]):
    import app.webhooks.whatsapp as wa

    def fake_get_or_create(**_kwargs):
        return {
            "id": 500,
            "channel": "whatsapp",
            "external_user_id": "wa:15551234567",
            "session_id": "s_sim",
            "state": None,
            "handoff_status": handoff_state["status"],
        }

    def fake_update_state(_cid, new_state):
        if new_state is not None:
            state_updates.append(new_state)

    def fake_update_handoff(_cid, status):
        handoff_state["status"] = status

    monkeypatch.setattr(wa, "get_or_create_conversation", fake_get_or_create)
    monkeypatch.setattr(wa, "update_conversation_state", fake_update_state)
    monkeypatch.setattr(wa, "update_handoff_status", fake_update_handoff)
    monkeypatch.setattr(wa, "enqueue_handoff_email", lambda **_kwargs: None)

    seen = set()

    def fake_insert_message(**kwargs):
        msg_id = kwargs.get("provider_message_id")
        if msg_id in seen:
            return None
        seen.add(msg_id)
        return 1

    monkeypatch.setattr(wa, "insert_message", fake_insert_message)


def test_whatsapp_simulator_menu_and_buttons(client, monkeypatch):
    import app.settings as settings_mod
    from app.services.whatsapp_mock import clear_mock_outbox, get_mock_outbox
    from app.bot.whatsapp_flow import MENU_CONSULTATION, MENU_PROJECTS, MENU_HUMAN

    settings_mod.settings.wa_mock_send = True
    settings_mod.settings.wa_access_token = "mock"
    settings_mod.settings.wa_phone_number_id = "mock"

    handoff_state = {"status": "bot"}
    state_updates: list[str] = []
    _setup_mocking(monkeypatch, handoff_state, state_updates)
    clear_mock_outbox()

    resp = client.post("/webhook/whatsapp", json=_payload_text("wamid-100", "hi"))
    assert resp.status_code == 200

    outbox = get_mock_outbox()
    assert outbox
    last = outbox[-1]
    assert last["type"] == "interactive"
    assert last["body_text"]
    button_ids = {btn["id"] for btn in last["buttons"]}
    assert {MENU_CONSULTATION, MENU_PROJECTS, MENU_HUMAN}.issubset(button_ids)
    assert last["timestamp"]


def test_whatsapp_simulator_category_selection(client, monkeypatch):
    import app.settings as settings_mod
    from app.services.whatsapp_mock import clear_mock_outbox, get_mock_outbox

    settings_mod.settings.wa_mock_send = True
    settings_mod.settings.wa_access_token = "mock"
    settings_mod.settings.wa_phone_number_id = "mock"

    handoff_state = {"status": "bot"}
    state_updates: list[str] = []
    _setup_mocking(monkeypatch, handoff_state, state_updates)
    clear_mock_outbox()

    resp = client.post("/webhook/whatsapp", json=_payload_button_reply("wamid-101", "MENU_PROJECTS"))
    assert resp.status_code == 200

    outbox = get_mock_outbox()
    assert outbox
    last = outbox[-1]
    assert last["type"] == "interactive"
    button_titles = {btn["title"] for btn in last["buttons"]}
    assert {"Villas", "Commercial"}.issubset(button_titles)
    assert "PROJECTS_MENU" in state_updates

    resp2 = client.post("/webhook/whatsapp", json=_payload_list_reply("wamid-102", "PROJECT_VILLAS"))
    assert resp2.status_code == 200
    assert len(get_mock_outbox()) >= 2


def test_whatsapp_simulator_handoff_stops_bot(client, monkeypatch):
    import app.settings as settings_mod
    from app.services.whatsapp_mock import clear_mock_outbox, get_mock_outbox

    settings_mod.settings.wa_mock_send = True
    settings_mod.settings.wa_access_token = "mock"
    settings_mod.settings.wa_phone_number_id = "mock"

    handoff_state = {"status": "bot"}
    state_updates: list[str] = []
    _setup_mocking(monkeypatch, handoff_state, state_updates)
    clear_mock_outbox()

    resp = client.post("/webhook/whatsapp", json=_payload_button_reply("wamid-103", "MENU_HUMAN"))
    assert resp.status_code == 200
    assert handoff_state["status"] == "human"
    outbox = get_mock_outbox()
    assert outbox
    outbox_len = len(outbox)

    resp2 = client.post("/webhook/whatsapp", json=_payload_text("wamid-104", "I need help"))
    assert resp2.status_code == 200
    assert len(get_mock_outbox()) == outbox_len

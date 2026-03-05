def _sample_payload(message_id: str, message_type: str = "text", action_id: str | None = None):
    message = {
        "id": message_id,
        "from": "15551234567",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": "Hi"}
    elif message_type == "interactive":
        if action_id:
            message["interactive"] = {
                "type": "button_reply",
                "button_reply": {"id": action_id, "title": "Tap"},
            }
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


def test_whatsapp_verification_success_and_fail(client, monkeypatch):
    import app.webhooks.whatsapp as wa

    monkeypatch.setattr(wa.settings, "wa_verify_token", "verify_me")
    ok = client.get("/webhook/whatsapp?hub.verify_token=verify_me&hub.challenge=abc123")
    assert ok.status_code == 200
    assert ok.text == "abc123"

    bad = client.get("/webhook/whatsapp?hub.verify_token=wrong&hub.challenge=abc123")
    assert bad.status_code == 403


def test_whatsapp_inbound_text_sends_main_menu(client, monkeypatch):
    import app.webhooks.whatsapp as wa
    import app.bot.whatsapp_flow as flow

    sent = {"buttons": None}

    class FakeClient:
        def send_buttons(self, **kwargs):
            sent["buttons"] = kwargs
            return {"messages": [{"id": "out-1"}]}

        def send_text(self, **_kwargs):
            return {"messages": [{"id": "out-2"}]}

        def send_list(self, **_kwargs):
            return {"messages": [{"id": "out-3"}]}

    monkeypatch.setattr(wa, "get_whatsapp_client", lambda: FakeClient())

    convo = {
        "id": 10,
        "channel": "whatsapp",
        "external_user_id": "wa:15551234567",
        "session_id": "s_demo",
        "state": None,
        "handoff_status": "bot",
    }
    monkeypatch.setattr(wa, "get_or_create_conversation", lambda **_kwargs: convo)
    monkeypatch.setattr(wa, "insert_message", lambda **_kwargs: 1)
    monkeypatch.setattr(wa, "update_conversation_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wa, "update_handoff_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wa, "enqueue_handoff_email", lambda **_kwargs: None)

    class DummySession:
        def __init__(self, state="WELCOME"):
            self.state = state
            self.data = {}

    session_state = {"state": "WELCOME"}

    monkeypatch.setattr(flow, "get_session", lambda _sid: DummySession(session_state["state"]))
    monkeypatch.setattr(flow, "set_state", lambda _sid, state: session_state.update({"state": state}))

    resp = client.post("/webhook/whatsapp", json=_sample_payload("wamid-1"))
    assert resp.status_code == 200
    assert sent["buttons"]
    button_ids = [b["id"] for b in sent["buttons"]["buttons"]]
    assert button_ids == ["MENU_CONSULTATION", "MENU_PROJECTS", "MENU_HUMAN"]


def test_whatsapp_handoff_stops_bot_responses(client, monkeypatch):
    import app.webhooks.whatsapp as wa
    import app.bot.whatsapp_flow as flow

    calls = {"send_text": 0}

    class FakeClient:
        def send_text(self, **_kwargs):
            calls["send_text"] += 1
            return {"messages": [{"id": f"out-{calls['send_text']}"}]}

        def send_buttons(self, **_kwargs):
            calls["send_text"] += 1
            return {"messages": [{"id": f"out-{calls['send_text']}"}]}

        def send_list(self, **_kwargs):
            calls["send_text"] += 1
            return {"messages": [{"id": f"out-{calls['send_text']}"}]}

    monkeypatch.setattr(wa, "get_whatsapp_client", lambda: FakeClient())

    state = {"handoff": "bot"}

    def fake_get_or_create(**_kwargs):
        return {
            "id": 20,
            "channel": "whatsapp",
            "external_user_id": "wa:15551234567",
            "session_id": "s_demo",
            "state": None,
            "handoff_status": state["handoff"],
        }

    def fake_update_handoff_status(_cid, status):
        state["handoff"] = status

    monkeypatch.setattr(wa, "get_or_create_conversation", fake_get_or_create)
    monkeypatch.setattr(wa, "update_handoff_status", fake_update_handoff_status)
    monkeypatch.setattr(wa, "update_conversation_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wa, "enqueue_handoff_email", lambda **_kwargs: None)

    seen = set()

    def fake_insert_message(**kwargs):
        msg_id = kwargs.get("provider_message_id")
        if msg_id in seen:
            return None
        seen.add(msg_id)
        return 1

    monkeypatch.setattr(wa, "insert_message", fake_insert_message)

    class DummySession:
        def __init__(self, state="WELCOME"):
            self.state = state
            self.data = {}

    monkeypatch.setattr(flow, "get_session", lambda _sid: DummySession("WELCOME"))
    monkeypatch.setattr(flow, "set_state", lambda *_args, **_kwargs: None)

    payload = _sample_payload("wamid-2", message_type="interactive", action_id="MENU_HUMAN")
    resp = client.post("/webhook/whatsapp", json=payload)
    assert resp.status_code == 200
    assert state["handoff"] == "human"
    assert calls["send_text"] == 1

    resp2 = client.post("/webhook/whatsapp", json=_sample_payload("wamid-3"))
    assert resp2.status_code == 200
    assert calls["send_text"] == 1


def test_whatsapp_deduplicates_provider_message_id(client, monkeypatch):
    import app.webhooks.whatsapp as wa
    import app.bot.whatsapp_flow as flow

    calls = {"send_buttons": 0}

    class FakeClient:
        def send_buttons(self, **_kwargs):
            calls["send_buttons"] += 1
            return {"messages": [{"id": "out-1"}]}

    monkeypatch.setattr(wa, "get_whatsapp_client", lambda: FakeClient())
    monkeypatch.setattr(wa, "update_conversation_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wa, "update_handoff_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wa, "enqueue_handoff_email", lambda **_kwargs: None)

    convo = {
        "id": 30,
        "channel": "whatsapp",
        "external_user_id": "wa:15551234567",
        "session_id": "s_demo",
        "state": None,
        "handoff_status": "bot",
    }
    monkeypatch.setattr(wa, "get_or_create_conversation", lambda **_kwargs: convo)

    seen = set()

    def fake_insert_message(**kwargs):
        msg_id = kwargs.get("provider_message_id")
        if msg_id in seen:
            return None
        seen.add(msg_id)
        return 1

    monkeypatch.setattr(wa, "insert_message", fake_insert_message)

    class DummySession:
        def __init__(self, state="WELCOME"):
            self.state = state
            self.data = {}

    monkeypatch.setattr(flow, "get_session", lambda _sid: DummySession("WELCOME"))
    monkeypatch.setattr(flow, "set_state", lambda *_args, **_kwargs: None)

    payload = _sample_payload("wamid-9")
    resp1 = client.post("/webhook/whatsapp", json=payload)
    resp2 = client.post("/webhook/whatsapp", json=payload)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert calls["send_buttons"] == 1

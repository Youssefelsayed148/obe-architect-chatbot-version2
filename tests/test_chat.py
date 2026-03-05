from app.schemas import ChatMessageOut
from redis.exceptions import RedisError


def test_chat_message_returns_schema_and_generates_session_id(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "rate_limit", lambda *_args, **_kwargs: None)
    captured_analytics = {}
    monkeypatch.setattr(main, "insert_analytics_event", lambda **kwargs: captured_analytics.update(kwargs))

    captured = {}

    def fake_handle_message(session_id, msg):
        captured["session_id"] = session_id
        return {
            "session_id": session_id,
            "messages": [{"type": "text", "text": "ok"}],
            "buttons": [],
            "form": None,
        }

    monkeypatch.setattr(main, "handle_message", fake_handle_message)

    payload = {
        "channel": "web",
        "user_id": "u-1",
        "session_id": None,
        "text": None,
        "button_id": None,
    }

    resp = client.post("/chat/message", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    ChatMessageOut.model_validate(body)
    assert body["session_id"].startswith("s_")
    assert captured["session_id"] == body["session_id"]
    assert captured_analytics["event_name"] == "user_message"
    assert captured_analytics["route_taken"] == "guided"
    assert captured_analytics["retrieval_top_score"] is None
    assert captured_analytics["retrieval_k"] is None
    assert captured_analytics["fallback_reason"] is None


def test_chat_message_returns_503_when_redis_unavailable(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "rate_limit", lambda *_args, **_kwargs: (_ for _ in ()).throw(RedisError("redis down")))

    payload = {
        "channel": "web",
        "user_id": "u-1",
        "session_id": None,
        "text": None,
        "button_id": None,
    }

    resp = client.post("/chat/message", json=payload)
    assert resp.status_code == 503

from fastapi import HTTPException


def test_rate_limit_triggers_after_n_requests(client, monkeypatch):
    import app.main as main

    counts = {}

    def fake_rate_limit(_request, key, limit, window_seconds):
        _ = (limit, window_seconds)
        if not key.startswith("user:"):
            return
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 2:
            raise HTTPException(status_code=429, detail="Too many requests")

    monkeypatch.setattr(main, "rate_limit", fake_rate_limit)
    monkeypatch.setattr(
        main,
        "handle_message",
        lambda session_id, _msg: {
            "session_id": session_id,
            "messages": [{"type": "text", "text": "ok"}],
            "buttons": [],
            "form": None,
        },
    )

    payload = {"channel": "web", "user_id": "rate-user", "session_id": "s_fixed"}

    assert client.post("/chat/message", json=payload).status_code == 200
    assert client.post("/chat/message", json=payload).status_code == 200
    assert client.post("/chat/message", json=payload).status_code == 429

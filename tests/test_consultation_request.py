def test_consultation_request_success(client, monkeypatch):
    import app.main as main

    captured = {}

    def fake_insert_consultation_lead_and_enqueue_email(**kwargs):
        captured.update(kwargs)
        return 123

    monkeypatch.setattr(
        main,
        "insert_consultation_lead_and_enqueue_email",
        fake_insert_consultation_lead_and_enqueue_email,
    )
    monkeypatch.setattr(main.settings, "leads_notify_to", "jojgame10@gmail.com")

    payload = {
        "name": "John Doe",
        "phone": "+971501112233",
        "email": "john@example.com",
        "consultant_type": "Architectural Design",
        "source": "chatbot",
        "session_id": "s_demo_1",
    }

    resp = client.post("/consultation/request", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "lead_id": 123}
    assert captured["phone"] == "+971501112233"
    assert captured["consultant_type"] == "Architectural Design"
    assert captured["notify_to"] == "jojgame10@gmail.com"


def test_consultation_request_rejects_invalid_phone(client):
    payload = {
        "name": "John Doe",
        "phone": "45554",
        "email": "john@example.com",
        "consultant_type": None,
        "source": "chatbot",
    }

    resp = client.post("/consultation/request", json=payload)
    assert resp.status_code == 422

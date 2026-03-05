def test_analytics_event_created(client, monkeypatch):
    import app.main as main

    captured = {}

    def fake_insert_analytics_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(main, "insert_analytics_event", fake_insert_analytics_event)

    payload = {
        "event_name": "project_category_click",
        "category": "Villas",
        "department": "Residential",
        "url": "https://obearchitects.com/obe/projects.php#villas",
        "session_id": "s_demo_1",
        "user_id": "demo_user",
        "source": "chatbot",
    }

    resp = client.post("/analytics/event", json=payload)
    assert resp.status_code == 201
    assert resp.json() == {"ok": True}
    assert captured["event_name"] == "project_category_click"
    assert captured["category"] == "Villas"
    assert captured["department"] == "Residential"


def test_analytics_event_falls_back_to_category_for_department(client, monkeypatch):
    import app.main as main

    captured = {}

    def fake_insert_analytics_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(main, "insert_analytics_event", fake_insert_analytics_event)

    payload = {
        "event_name": "project_category_click",
        "category": "Commercial",
        "url": "https://obearchitects.com/obe/projects.php#commercial",
        "source": "chatbot",
    }

    resp = client.post("/analytics/event", json=payload)
    assert resp.status_code == 201
    assert captured["department"] == "Commercial"


def test_analytics_event_rejects_missing_department_and_category(client):
    payload = {
        "event_name": "project_category_click",
        "url": "https://obearchitects.com/obe/projects.php#villas",
        "source": "chatbot",
    }

    resp = client.post("/analytics/event", json=payload)
    assert resp.status_code == 422


def test_analytics_event_rejects_invalid_event_name(client):
    payload = {
        "event_name": "unknown_event",
        "category": "Villas",
        "url": "https://obearchitects.com/obe/projects.php#villas",
        "source": "chatbot",
    }

    resp = client.post("/analytics/event", json=payload)
    assert resp.status_code == 422

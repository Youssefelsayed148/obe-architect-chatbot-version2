def test_admin_leads_without_api_key_is_unauthorized(client):
    resp = client.get("/admin/leads")
    assert resp.status_code in (401, 403)


def test_admin_leads_with_correct_api_key_returns_items(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "admin_api_key", "test-secret")
    monkeypatch.setattr(
        main,
        "list_leads",
        lambda limit=50: [
            {
                "id": 1,
                "created_at": "2026-02-21T00:00:00Z",
                "name": "Jane",
                "phone": "+10000000000",
                "email": "jane@example.com",
                "project_type": "Villa",
                "source": "web",
                "session_id": "s_abc123",
            }
        ],
    )

    resp = client.get("/admin/leads", headers={"X-API-Key": "test-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["items"][0]["name"] == "Jane"


def test_admin_analytics_clicks_by_department_without_api_key_is_unauthorized(client):
    resp = client.get("/admin/analytics/clicks-by-department")
    assert resp.status_code in (401, 403)


def test_admin_analytics_clicks_by_department_with_invalid_api_key_is_unauthorized(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "admin_api_key", "test-secret")
    resp = client.get("/admin/analytics/clicks-by-department", headers={"X-API-Key": "wrong-secret"})
    assert resp.status_code in (401, 403)


def test_admin_analytics_clicks_by_department_returns_aggregated_items(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "admin_api_key", "test-secret")
    monkeypatch.setattr(
        main,
        "get_click_counts_by_department",
        lambda start=None, end=None: [
            {"department": "Residential", "clicks": 42},
            {"department": "Commercial", "clicks": 17},
            {"department": "unknown", "clicks": 3},
        ],
    )

    resp = client.get("/admin/analytics/clicks-by-department", headers={"X-API-Key": "test-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0] == {"department": "Residential", "clicks": 42}
    assert body["items"][2] == {"department": "unknown", "clicks": 3}
    assert body["total_clicks"] == 62
    assert body["range"] == {"start": None, "end": None}


def test_admin_leads_rejects_invalid_limit(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "admin_api_key", "test-secret")
    resp = client.get("/admin/leads?limit=0", headers={"X-API-Key": "test-secret"})
    assert resp.status_code == 422

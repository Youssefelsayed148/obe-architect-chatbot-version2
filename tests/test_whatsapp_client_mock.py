def test_whatsapp_client_mock_send_returns_request_payload(monkeypatch):
    from app.services.whatsapp_client import WhatsAppClient
    from app.services import whatsapp_client as wa_client_module

    monkeypatch.setattr(wa_client_module.settings, "wa_mock_send", True)

    client = WhatsAppClient(
        access_token="mock_access",
        phone_number_id="mock_phone",
        graph_version="v20.0",
    )

    response = client.send_buttons(
        to="15550001111",
        body_text="Welcome",
        buttons=[{"id": "MENU_PROJECTS", "title": "View Projects"}],
    )

    assert response["mock"] is True
    assert response["messages"][0]["id"].startswith("mock-")
    assert response["request"]["type"] == "interactive"
    assert response["request"]["interactive"]["type"] == "button"

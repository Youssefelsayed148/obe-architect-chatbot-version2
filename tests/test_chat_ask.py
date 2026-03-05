def test_chat_ask_returns_404_when_feature_disabled(client, monkeypatch):
    import app.routers.chat_ask as chat_ask

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", False)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)

    response = client.post("/chat/ask", json={"question": "What services do you offer?"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Public RAG endpoint is disabled."


def test_chat_ask_writes_analytics_for_successful_rag(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    captured = {}
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_ask, "insert_analytics_event", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer="**Answer**\nCommercial work is available.",
            sources=[],
            confidence=0.91,
            route_taken="rag",
            retrieval_top_score=0.91,
            retrieval_k=5,
            fallback_reason=None,
        ),
    )

    response = client.post("/chat/ask", json={"question": "Tell me about commercial projects", "user_id": "u-1"})
    assert response.status_code == 200
    assert captured["event_name"] == "user_message"
    assert captured["route_taken"] == "rag"
    assert captured["retrieval_top_score"] == 0.91
    assert captured["retrieval_k"] == 5
    assert captured["fallback_reason"] is None


def test_chat_ask_writes_analytics_for_low_similarity_fallback(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    captured = {}
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_ask, "insert_analytics_event", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer="I don't have enough portfolio content to answer that precisely.",
            sources=[],
            confidence=0.62,
            route_taken="fallback",
            retrieval_top_score=0.62,
            retrieval_k=5,
            fallback_reason="low_similarity",
        ),
    )

    response = client.post("/chat/ask", json={"question": "Unknown question", "user_id": "u-2"})
    assert response.status_code == 200
    assert captured["event_name"] == "user_message"
    assert captured["route_taken"] == "fallback"
    assert captured["retrieval_top_score"] == 0.62
    assert captured["retrieval_k"] == 5
    assert captured["fallback_reason"] == "low_similarity"


def test_chat_ask_category_overview_sets_followup_step(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.store.redis_sessions import Session
    from app.services.rag_public import RagAnswerResult, ROUTE_CATEGORY_OVERVIEW

    captured = {"set_data": []}
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_ask, "get_session", lambda _sid: Session(state="WELCOME", data={"category_followup_step": 2}))

    def fake_set_data(session_id, key, value):
        captured["set_data"].append((session_id, key, value))

    monkeypatch.setattr(chat_ask, "set_data", fake_set_data)
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer="Villas Designed by OBE Architects\n\nKEY HIGHLIGHTS\n- **Location:** Dubai.",
            sources=[],
            confidence=0.8,
            follow_up_buttons=["Can you provide more information about the exterior design features?"],
            route_kind=ROUTE_CATEGORY_OVERVIEW,
            category_slug="villas",
        ),
    )

    response = client.post("/chat/ask", json={"question": "tell me about villas", "session_id": "s-1"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload.get("follow_up_buttons") or []) <= 1
    assert ("s-1", "last_category_slug", "villas") in captured["set_data"]
    assert ("s-1", "category_followup_step", 0) in captured["set_data"]

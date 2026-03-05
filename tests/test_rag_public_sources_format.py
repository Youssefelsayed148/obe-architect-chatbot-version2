def test_chat_ask_returns_rich_sources_objects(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer="OBE has villa projects.",
            sources=[
                {
                    "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                    "title": "The Court Villa",
                    "location": "Dubai",
                    "status": "Completed",
                    "size": "2,845 sq.ft",
                    "overview": "Villa design with open and green spaces.",
                }
            ],
            confidence=0.81,
        ),
    )

    response = client.post("/chat/ask", json={"question": "Tell me more about Court Villa"})
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["sources"], list)
    assert payload["sources"]
    source = payload["sources"][0]
    assert sorted(source.keys()) == ["location", "overview", "size", "status", "title", "url"]
    assert source["url"].startswith("https://")
    assert source["title"]
    assert payload["answer_format"] == "markdown"


def test_chat_ask_follow_up_buttons_single_or_empty(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer="Villas Designed by OBE Architects\n\nKEY HIGHLIGHTS\n- **Location:** Dubai.",
            sources=[],
            confidence=0.8,
            follow_up_buttons=["Can you provide more information about the exterior design features?"],
        ),
    )

    response = client.post("/chat/ask", json={"question": "tell me about villas"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload.get("follow_up_buttons") or []) <= 1


def test_chat_ask_accepts_context_urls(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    captured = {}
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)

    def fake_answer_question(**kwargs):
        captured.update(kwargs)
        return RagAnswerResult(answer="Title\n\n**Key highlights**\n- **Detail:** ok", sources=[], confidence=0.6)

    monkeypatch.setattr(chat_ask, "answer_question", fake_answer_question)

    response = client.post(
        "/chat/ask",
        json={
            "question": "tell me more about Court Villa",
            "context_urls": [
                "https://obearchitects.com/obe/project-detail.php?id=65",
                "https://obearchitects.com/obe/project-detail.php?id=65",
            ],
        },
    )
    assert response.status_code == 200
    assert captured.get("context_urls") == ["https://obearchitects.com/obe/project-detail.php?id=65"]


def test_chat_ask_ignores_context_urls_for_explicit_category(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    captured = {}
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)

    def fake_answer_question(**kwargs):
        captured.update(kwargs)
        return RagAnswerResult(
            answer="Commercial Projects by OBE Architects\n\nKEY HIGHLIGHTS\n- **Location:** Dubai.",
            sources=[],
            confidence=0.8,
        )

    monkeypatch.setattr(chat_ask, "answer_question", fake_answer_question)

    response = client.post(
        "/chat/ask",
        json={
            "question": "tell me about commercial projects",
            "context_urls": ["https://obearchitects.com/obe/project-detail.php?id=65"],
        },
    )
    assert response.status_code == 200
    assert captured.get("context_urls") is None

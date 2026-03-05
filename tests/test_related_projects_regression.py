def test_related_projects_are_real_projects_and_limited(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    import app.services.rag_public as rag_public

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.1)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 8000)

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/about-us.php",
                "title": "About OBE",
                "chunk_text": "Mission and values.",
                "score": 0.99,
                "doc_type": "page",
            },
            {
                "url": "https://obearchitects.com/obe/services.php",
                "title": "Services",
                "chunk_text": "Architecture and interiors.",
                "score": 0.98,
                "doc_type": "page",
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=54",
                "title": "Community Retail Center - Design Competition",
                "chunk_text": "Commercial project in Dubai.",
                "score": 0.97,
                "doc_type": "project",
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=60",
                "title": "Business Center At Al Quoz",
                "chunk_text": "Commercial complex on Sheikh Zayed Road.",
                "score": 0.96,
                "doc_type": "project",
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=24",
                "title": "Al Marmoum Mosque",
                "chunk_text": "Large built-up area project.",
                "score": 0.95,
                "doc_type": "project",
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "chunk_text": "Luxury residential project in Dubai.",
                "score": 0.94,
                "doc_type": "project",
            },
        ],
    )

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "Commercial Projects\n\n**Key highlights**\n- **Location:** Dubai"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    response = client.post(
        "/chat/ask",
        json={"question": "Tell me about commercial projects in Dubai", "top_k": 10},
    )
    assert response.status_code == 200
    data = response.json()

    assert "sources" in data
    sources = data["sources"]
    assert isinstance(sources, list)
    assert len(sources) <= 3

    for source in sources:
        assert "url" in source
        url = str(source["url"]).lower()
        assert "project-detail.php?id=" in url
        assert "about" not in url
        assert "service" not in url
        assert "mission" not in url
        assert "home" not in url


def test_related_projects_regression_allows_empty_sources(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    import app.services.rag_public as rag_public

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.1)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 8000)

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/about-us.php",
                "title": "About OBE",
                "chunk_text": "Mission and values.",
                "score": 0.99,
                "doc_type": "page",
            }
        ],
    )

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "OBE\n\n**Key highlights**\n- **Detail:** Not specified in the provided sources."

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    response = client.post(
        "/chat/ask",
        json={"question": "Tell me about commercial projects in Dubai"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert isinstance(data["sources"], list)
    assert data["sources"] == []

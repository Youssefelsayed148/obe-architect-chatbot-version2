import re

import pytest


def _normalize_tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9\s]+", " ", (text or "").lower())
    return {token for token in normalized.split() if token}


def _token_overlap_ratio(a: str, b: str) -> float:
    ta = _normalize_tokens(a)
    tb = _normalize_tokens(b)
    if not ta or not tb:
        return 0.0
    # Coverage-style overlap: how much of the shorter answer's vocabulary is preserved.
    return len(ta & tb) / float(min(len(ta), len(tb)))


def test_chat_ask_is_reasonably_stable_for_same_question(client, monkeypatch):
    import app.routers.chat_ask as chat_ask
    import app.services.rag_public as rag_public
    from app.rag.ollama_client import OllamaClient

    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.1)
    monkeypatch.setattr(rag_public.settings, "rag_public_top_k", 5)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 7000)

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=54",
                "title": "Community Retail Center - Design Competition",
                "doc_type": "project",
                "chunk_text": "Aswaaq community retail center design competition in Dubai.",
                "score": 0.93,
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=60",
                "title": "Business Center At Al Quoz",
                "doc_type": "project",
                "chunk_text": "Business center on Sheikh Zayed Road in Dubai.",
                "score": 0.91,
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "doc_type": "project",
                "chunk_text": "Luxury residential project in Dubai.",
                "score": 0.89,
            },
        ],
    )

    try:
        probe = OllamaClient(timeout_seconds=8.0)
        probe.chat(
            messages=[{"role": "user", "content": "Reply with one short sentence."}],
            options={"temperature": 0.0, "top_p": 0.9},
        )
    except Exception as exc:  # pragma: no cover - environment-dependent availability
        pytest.skip(f"Ollama is unavailable for stability regression test: {exc}")

    payload = {"question": "Tell me about commercial projects in Dubai", "top_k": 5}
    response_a = client.post("/chat/ask", json=payload)
    response_b = client.post("/chat/ask", json=payload)

    assert response_a.status_code == 200
    assert response_b.status_code == 200

    data_a = response_a.json()
    data_b = response_b.json()

    urls_a = {
        str(source.get("url"))
        for source in data_a.get("sources", [])
        if isinstance(source, dict) and source.get("url")
    }
    urls_b = {
        str(source.get("url"))
        for source in data_b.get("sources", [])
        if isinstance(source, dict) and source.get("url")
    }

    assert urls_a == urls_b
    overlap = _token_overlap_ratio(str(data_a.get("answer", "")), str(data_b.get("answer", "")))
    assert overlap >= 0.70

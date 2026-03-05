from __future__ import annotations

import json
from pathlib import Path

import pytest


GOLDEN_PATH = Path("tests/golden/golden_questions.jsonl")
def _load_refusal_questions() -> list[dict]:
    rows: list[dict] = []
    with GOLDEN_PATH.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if item.get("must_refuse"):
                rows.append(item)
    return rows


@pytest.mark.parametrize("item", _load_refusal_questions(), ids=lambda item: item["id"])
def test_chat_ask_refusal_cases_return_safe_fallback(client, monkeypatch, item):
    import app.routers.chat_ask as chat_ask
    from app.services.rag_public import RagAnswerResult

    min_conf = 0.55
    monkeypatch.setattr(chat_ask.settings, "rag_public_enabled", True)
    monkeypatch.setattr(chat_ask.settings, "rag_public_min_confidence", min_conf)
    monkeypatch.setattr(chat_ask, "rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_ask,
        "answer_question",
        lambda **_kwargs: RagAnswerResult(
            answer=(
                "OBE Portfolio Highlights\n\n"
                "KEY HIGHLIGHTS\n"
                "• **Summary:** I couldn't retrieve enough portfolio text to answer that precisely.\n"
                "• **Try:** Ask about a specific project name, or choose a category (Villas / Commercial / Sports / Education).\n"
                "• **Next step:** Tell me your city (e.g., Dubai) or the project type.\n\n"
                "RELATED PROJECTS\n\n"
                "Follow-up: Want a quick shortlist of notable projects in this category?"
            ),
            sources=[],
            confidence=min_conf - 0.2,
        ),
    )

    response = client.post("/chat/ask", json={"question": item["question"]})
    assert response.status_code == 200
    data = response.json()
    assert "KEY HIGHLIGHTS" in data["answer"]
    assert "RELATED PROJECTS" in data["answer"]
    assert "I don't know based on the available sources." not in data["answer"]
    assert data["sources"] == []
    assert float(data["confidence"]) < float(chat_ask.settings.rag_public_min_confidence)

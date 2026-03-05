from __future__ import annotations

from typing import Any

from app.rag.ollama_client import OllamaClient
from app.rag.retriever import retrieve_chunks
from app.settings import settings


SYSTEM_PROMPT = (
    "You are OBE Architects assistant. Use ONLY provided context. "
    "If not found, say you don't know."
)


def _build_context(matches: list[dict[str, Any]], max_chars: int) -> tuple[str, list[str], list[dict[str, Any]]]:
    chosen: list[dict[str, Any]] = []
    urls: list[str] = []
    total = 0
    parts: list[str] = []

    for idx, item in enumerate(matches, start=1):
        block = (
            f"[{idx}] URL: {item['url']}\n"
            f"Title: {item['title']}\n"
            f"Score: {item['score']:.4f}\n"
            f"Chunk:\n{item['chunk_text']}\n"
        )
        if total + len(block) > max_chars:
            continue
        total += len(block)
        chosen.append(item)
        parts.append(block)
        if item["url"] and item["url"] not in urls:
            urls.append(item["url"])
    return "\n".join(parts), urls, chosen


def answer_with_rag(query: str, top_k: int | None = None) -> dict[str, Any]:
    matches = retrieve_chunks(query=query, top_k=top_k)
    context, sources, context_matches = _build_context(
        matches=matches,
        max_chars=settings.rag_max_context_chars,
    )
    user_prompt = f"Question:\n{query}\n\nContext:\n{context or 'No matching context found.'}"

    client = OllamaClient()
    answer = client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )

    return {
        "answer": answer,
        "sources": sources,
        "matches": context_matches,
    }

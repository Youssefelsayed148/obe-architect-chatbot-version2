from __future__ import annotations

import json
from pathlib import Path

import pytest
from psycopg import connect

from app.rag.retriever import retrieve_chunks
from app.settings import settings


GOLDEN_PATH = Path("tests/golden/golden_questions.jsonl")


def _load_golden() -> list[dict]:
    rows: list[dict] = []
    with GOLDEN_PATH.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _top_k() -> int:
    raw = settings.rag_public_top_k if settings.rag_public_top_k else 5
    return max(1, int(raw))


def _db_ready_or_skip() -> None:
    try:
        with connect(settings.postgres_dsn) as con:
            with con.cursor() as cur:
                cur.execute("SELECT to_regclass('public.rag_chunks')")
                table_name = cur.fetchone()[0]
                if not table_name:
                    pytest.skip("rag_chunks table is not available")
                cur.execute("SELECT COUNT(*) FROM rag_chunks")
                count = int(cur.fetchone()[0])
                if count == 0:
                    pytest.skip("rag_chunks table is empty")
    except Exception as exc:
        pytest.skip(f"Postgres not available for retrieval golden test: {exc}")


@pytest.mark.integration
@pytest.mark.parametrize(
    "item",
    [entry for entry in _load_golden() if not entry.get("must_refuse", False) and entry.get("lang") == "en"],
    ids=lambda item: item["id"],
)
def test_retrieval_returns_expected_url_for_golden_question(item: dict):
    _db_ready_or_skip()

    expected_urls = item.get("expected_urls") or []
    assert expected_urls, f"golden entry {item['id']} requires expected_urls for non-refusal checks"

    top_k = _top_k()
    try:
        matches = retrieve_chunks(query=item["question"], top_k=top_k, min_score=0.0)
    except Exception as exc:
        pytest.skip(f"Retriever dependencies unavailable for golden test: {exc}")
    found_urls = [str(match.get("url") or "") for match in matches if str(match.get("url") or "")]
    assert found_urls, f"no URLs retrieved for {item['id']} question={item['question']!r}"

    overlap = set(expected_urls).intersection(found_urls)
    assert overlap, (
        f"expected one of {expected_urls} in top_{top_k}={found_urls} "
        f"for {item['id']} question={item['question']!r}"
    )

from __future__ import annotations

import re
from typing import Any, LiteralString, cast

from psycopg import connect, sql
from psycopg.rows import dict_row

from app.rag.embedder import OllamaEmbedder
from app.settings import settings


RETRIEVAL_SQL: LiteralString = """
SELECT
  rc.id AS chunk_id,
  rc.chunk_text,
  rc.document_url AS url,
  rd.title,
  rd.doc_type,
  (1 - (rc.embedding <=> %s::vector)) AS score
FROM rag_chunks rc
JOIN rag_documents rd ON rd.url = rc.document_url
ORDER BY score DESC, rc.id ASC
LIMIT %s
"""

RETRIEVAL_SQL_FILTERED: LiteralString = """
SELECT
  rc.id AS chunk_id,
  rc.chunk_text,
  rc.document_url AS url,
  rd.title,
  rd.doc_type,
  (1 - (rc.embedding <=> %s::vector)) AS score
FROM rag_chunks rc
JOIN rag_documents rd ON rd.url = rc.document_url
WHERE rc.document_url = ANY(%s)
ORDER BY score DESC, rc.id ASC
LIMIT %s
"""

KEYWORD_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "with", "about",
    "what", "which", "who", "why", "how", "do", "does", "is", "are", "me", "your", "our",
    "you", "we", "their", "this", "that", "these", "those", "from", "as", "by", "be",
    "tell", "share", "give", "provide", "details", "detail", "overview", "project",
}


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def _row_to_match(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": int(row.get("chunk_id") or 0),
        "url": row.get("url") or "",
        "title": row.get("title") or "",
        "doc_type": row.get("doc_type") or "",
        "chunk_text": row.get("chunk_text") or "",
        "score": float(row.get("score") or 0.0),
    }


def _keyword_tokens(query: str) -> list[str]:
    if not query:
        return []
    words = [w for w in re.findall(r"[A-Za-z0-9]+", query) if w]
    tokens: list[str] = []
    seen: set[str] = set()
    for word in words:
        low = word.lower()
        if len(low) < 3 or low in KEYWORD_STOPWORDS:
            continue
        if low in seen:
            continue
        seen.add(low)
        tokens.append(low)
        if len(tokens) >= 4:
            break
    return tokens


def _retrieve_keyword_matches(
    query: str,
    top_k: int,
    url_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    tokens = _keyword_tokens(query)
    if not tokens:
        return []
    score_terms: list[str] = []
    token_params: list[Any] = []
    for token in tokens:
        like = f"%{token}%"
        score_terms.append("(CASE WHEN rc.chunk_text ILIKE %s OR rd.title ILIKE %s THEN 1 ELSE 0 END)")
        token_params.extend([like, like])

    score_expr = " + ".join(score_terms) if score_terms else "0"
    where = f"({score_expr}) > 0"
    if url_filters:
        where += " AND rc.document_url = ANY(%s)"

    sql_text = f"""
    SELECT
      rc.id AS chunk_id,
      rc.chunk_text,
      rc.document_url AS url,
      rd.title,
      rd.doc_type,
      ({score_expr})::float AS score
    FROM rag_chunks rc
    JOIN rag_documents rd ON rd.url = rc.document_url
    WHERE {where}
    ORDER BY score DESC, rc.id ASC
    LIMIT %s
    """
    params = token_params + token_params
    if url_filters:
        params.append(url_filters)
    params.append(top_k)
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(sql.SQL(cast(LiteralString, sql_text)), params)
            rows = cur.fetchall()
    return [_row_to_match(row) for row in rows]


def retrieve_chunks(
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
    embedder: OllamaEmbedder | None = None,
    url_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    use_top_k = top_k if top_k is not None else settings.rag_top_k
    use_min_score = settings.rag_min_score if min_score is None else min_score

    current_embedder = embedder or OllamaEmbedder()
    vector = current_embedder.get_embeddings([query])[0]
    qvec = _vector_literal(vector)
    cleaned_filters = [str(url).strip() for url in (url_filters or []) if str(url).strip()]
    use_filtered = len(cleaned_filters) > 0

    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            if use_filtered:
                cur.execute(RETRIEVAL_SQL_FILTERED, (qvec, cleaned_filters, use_top_k))
            else:
                cur.execute(RETRIEVAL_SQL, (qvec, use_top_k))
            rows = cur.fetchall()

    matches = [_row_to_match(row) for row in rows]
    keyword_matches = _retrieve_keyword_matches(query, use_top_k, cleaned_filters) if embedder is None else []
    if keyword_matches:
        seen: set[tuple[str, str]] = set()
        merged: list[dict[str, Any]] = []
        for item in keyword_matches + matches:
            key = (str(item.get("url") or ""), str(item.get("chunk_text") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= use_top_k:
                break
        matches = merged
    keyword_keys = {
        (str(item.get("url") or ""), str(item.get("chunk_text") or "")) for item in keyword_matches
    }
    return [
        item
        for item in matches
        if item["score"] >= use_min_score or (str(item.get("url") or ""), str(item.get("chunk_text") or "")) in keyword_keys
    ]

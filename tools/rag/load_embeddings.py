from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from psycopg import connect

from app.rag.embedder import OllamaEmbedder
from app.settings import settings
from tools.ingestion.utils import compute_sha256


@dataclass
class ChunkRecord:
    url: str
    title: str
    chunk_index: int
    chunk_text: str
    chunk_char_len: int


def parse_chunk_line(line: str) -> ChunkRecord | None:
    raw = line.strip()
    if not raw:
        return None
    payload = json.loads(raw)
    chunk_text = (payload.get("chunk_text") or "").strip()
    if not chunk_text:
        return None
    url = (payload.get("url") or "").strip()
    if not url:
        return None
    title = (payload.get("title") or "").strip()
    chunk_index = int(payload.get("chunk_index") or 0)
    chunk_char_len = int(payload.get("chunk_char_len") or len(chunk_text))
    return ChunkRecord(
        url=url,
        title=title,
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        chunk_char_len=chunk_char_len,
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def _chunk_source(url: str) -> str:
    return urlparse(url).netloc or "unknown"


def _upsert_batch(
    con,
    rows: list[ChunkRecord],
    vectors: list[list[float]],
    *,
    reembed: bool,
) -> dict[str, int]:
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    with con.cursor() as cur:
        for row, vector in zip(rows, vectors):
            cur.execute(
                """
                INSERT INTO rag_documents(url, title, source, content_hash, scraped_at_utc)
                VALUES (%s, %s, %s, %s, NULL)
                ON CONFLICT (url)
                DO UPDATE SET
                  title = EXCLUDED.title,
                  source = EXCLUDED.source,
                  content_hash = EXCLUDED.content_hash
                """,
                (row.url, row.title, _chunk_source(row.url), compute_sha256(row.chunk_text)),
            )

            if reembed:
                cur.execute(
                    """
                    INSERT INTO rag_chunks(
                      document_url, chunk_index, chunk_text, chunk_char_len, embedding, embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (document_url, chunk_index, embedding_model)
                    DO UPDATE SET
                      chunk_text = EXCLUDED.chunk_text,
                      chunk_char_len = EXCLUDED.chunk_char_len,
                      embedding = EXCLUDED.embedding,
                      created_at = now()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        row.url,
                        row.chunk_index,
                        row.chunk_text,
                        row.chunk_char_len,
                        _vector_literal(vector),
                        settings.ollama_embed_model,
                    ),
                )
                inserted = bool(cur.fetchone()[0])
                if inserted:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            else:
                cur.execute(
                    """
                    INSERT INTO rag_chunks(
                      document_url, chunk_index, chunk_text, chunk_char_len, embedding, embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (document_url, chunk_index, embedding_model)
                    DO NOTHING
                    RETURNING id
                    """,
                    (
                        row.url,
                        row.chunk_index,
                        row.chunk_text,
                        row.chunk_char_len,
                        _vector_literal(vector),
                        settings.ollama_embed_model,
                    ),
                )
                created = cur.fetchone()
                if created:
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1
    con.commit()
    return stats


def load_embeddings(
    *,
    chunks_path: str | Path = settings.rag_chunks_path,
    limit: int | None = None,
    reembed: bool = False,
    batch_size: int = settings.rag_batch_size,
) -> dict[str, int]:
    path = Path(chunks_path)
    if not path.exists():
        raise FileNotFoundError(f"Chunks file not found: {path}")

    embedder = OllamaEmbedder()
    stats = {
        "total_read": 0,
        "embedded": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failures": 0,
    }

    with connect(settings.postgres_dsn) as con:
        def _flush_batch(items: list[ChunkRecord]) -> None:
            if not items:
                return
            try:
                vectors = embedder.get_embeddings([item.chunk_text for item in items])
                stats["embedded"] += len(vectors)
                update = _upsert_batch(con, items, vectors, reembed=reembed)
                stats["inserted"] += update["inserted"]
                stats["updated"] += update["updated"]
                stats["skipped"] += update["skipped"]
            except Exception:
                stats["failures"] += len(items)

        batch: list[ChunkRecord] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stats["total_read"] += 1
                try:
                    parsed = parse_chunk_line(line)
                except Exception:
                    stats["failures"] += 1
                    continue
                if parsed is None:
                    stats["skipped"] += 1
                    continue
                batch.append(parsed)

                if limit and stats["embedded"] + len(batch) > limit:
                    batch = batch[: max(0, limit - stats["embedded"])]
                if not batch:
                    break
                if len(batch) >= batch_size or (limit and stats["embedded"] + len(batch) >= limit):
                    _flush_batch(batch)
                    batch = []
                if limit and stats["embedded"] >= limit:
                    break

        if batch and (not limit or stats["embedded"] < limit):
            _flush_batch(batch)

    return stats

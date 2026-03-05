from __future__ import annotations

import json

from psycopg import connect
from psycopg.rows import dict_row

from app.rag.retriever import retrieve_chunks
from app.settings import settings


def run_smoke(query: str = "OBE architects projects", top_k: int = 3) -> dict:
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS count FROM rag_documents")
            docs_count = int(cur.fetchone()["count"])
            cur.execute("SELECT COUNT(*) AS count FROM rag_chunks")
            chunks_count = int(cur.fetchone()["count"])

    matches = retrieve_chunks(query=query, top_k=top_k)
    result = {
        "rag_documents_count": docs_count,
        "rag_chunks_count": chunks_count,
        "sample_query": query,
        "matches": [
            {
                "url": m["url"],
                "title": m["title"],
                "score": m["score"],
                "preview": m["chunk_text"][:180].replace("\n", " ").strip(),
            }
            for m in matches
        ],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from tools.ingestion.extract_text import normalize_whitespace
from tools.ingestion.utils import read_jsonl, write_jsonl


NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text_for_chunking(text: str) -> str:
    normalized = normalize_whitespace(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines:
        return ""

    counts = Counter(lines)
    cleaned_lines = [
        line
        for line in lines
        if not (counts[line] >= 3 and len(line) < 80 and len(line.split()) <= 8)
    ]
    cleaned = "\n".join(cleaned_lines)
    return NEWLINES_RE.sub("\n\n", cleaned).strip()


def chunk_text(text: str, chunk_size_chars: int = 3200, overlap_chars: int = 250) -> list[str]:
    if chunk_size_chars <= overlap_chars:
        raise ValueError("chunk_size_chars must be larger than overlap_chars")
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    step = chunk_size_chars - overlap_chars
    while start < text_len:
        end = min(start + chunk_size_chars, text_len)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= text_len:
            break
        start += step
    return chunks


def chunk_documents(
    input_path: str | Path,
    output_path: str | Path,
    chunk_size_chars: int = 3200,
    overlap_chars: int = 250,
) -> dict:
    docs = read_jsonl(Path(input_path))
    chunks: list[dict] = []
    kept_docs = 0
    for doc in docs:
        cleaned = clean_text_for_chunking(doc.get("text", ""))
        if len(cleaned) < 200:
            continue
        kept_docs += 1
        for idx, part in enumerate(chunk_text(cleaned, chunk_size_chars=chunk_size_chars, overlap_chars=overlap_chars)):
            chunks.append(
                {
                    "url": doc.get("url", ""),
                    "title": doc.get("title", ""),
                    "chunk_index": idx,
                    "chunk_text": part,
                    "chunk_char_len": len(part),
                }
            )

    output = Path(output_path)
    write_jsonl(output, chunks)
    return {"docs_count": kept_docs, "chunks_count": len(chunks), "output_path": str(output)}


def smoke_validate_chunks(
    docs_path: str | Path,
    chunks_path: str | Path,
    sample_size: int = 3,
) -> dict:
    docs = read_jsonl(Path(docs_path))
    chunks = read_jsonl(Path(chunks_path))
    domain_counts = Counter(urlparse(item.get("url", "")).netloc for item in docs if item.get("url"))
    top_domains = [{"domain": d, "count": c} for d, c in domain_counts.most_common(10)]
    sample = [
        {
            "url": item.get("url", ""),
            "preview": (item.get("chunk_text", "")[:200]).replace("\n", " "),
        }
        for item in chunks[:sample_size]
    ]
    result = {
        "docs_count": len(docs),
        "chunks_count": len(chunks),
        "top_10_domains": top_domains,
        "sample_chunks": sample,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

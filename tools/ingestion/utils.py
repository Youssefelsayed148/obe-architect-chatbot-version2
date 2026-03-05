from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:
    import tldextract

    _TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=None)
except Exception:  # pragma: no cover - optional import fallback
    tldextract = None
    _TLD_EXTRACTOR = None


ASSET_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


def normalize_url(
    url: str,
    base_url: str,
    allowed_query_keys: Iterable[str],
) -> tuple[str | None, bool]:
    """Normalize URL for queue de-duplication and safe query filtering."""
    raw = urljoin(base_url, url.strip())
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None, False
    if not parsed.netloc:
        return None, False

    allowed = {k.strip().lower() for k in allowed_query_keys if k.strip()}
    query_pairs = []
    removed_unknown = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lowered = key.lower()
        if lowered in allowed:
            query_pairs.append((lowered, value))
        else:
            removed_unknown = True

    normalized_query = urlencode(sorted(query_pairs), doseq=True)
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            normalized_query,
            "",
        )
    )
    return normalized, removed_unknown


def is_same_registrable_domain(url: str, base_url: str, allow_subdomains: bool = False) -> bool:
    url_host = (urlparse(url).hostname or "").lower()
    base_host = (urlparse(base_url).hostname or "").lower()
    if not url_host or not base_host:
        return False
    if allow_subdomains:
        return url_host == base_host or url_host.endswith(f".{base_host}")

    if _TLD_EXTRACTOR is not None:
        ext_url = _TLD_EXTRACTOR(url_host)
        ext_base = _TLD_EXTRACTOR(base_host)
        if not ext_url.domain or not ext_url.suffix or not ext_base.domain or not ext_base.suffix:
            return False
        return (ext_url.domain, ext_url.suffix) == (ext_base.domain, ext_base.suffix)

    url_parts = url_host.split(".")
    base_parts = base_host.split(".")
    if len(url_parts) < 2 or len(base_parts) < 2:
        return False
    return ".".join(url_parts[-2:]) == ".".join(base_parts[-2:])


def is_in_path_scope(url: str, path_prefix: str) -> bool:
    path = urlparse(url).path or "/"
    wanted = path_prefix if path_prefix.startswith("/") else f"/{path_prefix}"
    return path.startswith(wanted)


def is_probable_asset(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return any(path.endswith(ext) for ext in ASSET_EXTENSIONS)


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def top_paths(urls: Iterable[str], top_n: int = 10) -> list[dict]:
    counts = Counter((urlparse(url).path or "/") for url in urls)
    return [{"path": path, "count": count} for path, count in counts.most_common(top_n)]

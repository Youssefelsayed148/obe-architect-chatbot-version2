from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse

from psycopg import connect
from psycopg.rows import dict_row

from app.rag.ollama_client import OllamaClient
from app.rag.retriever import retrieve_chunks
from app.settings import settings


logger = logging.getLogger("app.services.rag_public")

FALLBACK_FOLLOW_UP = "Want a quick shortlist of notable projects in this category?"

SYSTEM_PROMPT = """
You are OBE Assistant, representing OBE Architects.

Use ONLY the provided sources context.
Do not invent details. If information is missing, omit it.

Style:
- Professional, calm, and confident.
- Concise but informative.
- Slightly creative in wording, but grounded in context.
- Never mention internal logic, scores, or assumptions.
- Never say "I don't know based on the available sources."

Structure:
Title line

KEY HIGHLIGHTS
• **Label:** Value
(3-6 bullets maximum)

Optional:
Follow-up question: <one short, helpful question>

Rules:
- Only include details supported by the provided context.
- If a numeric detail is not clearly present in context, omit it.
- Avoid repetition.
- Keep the answer readable and elegant.
- For category overviews, prioritize these if present in sources: built-up area range, locations, and number of floors.
"""
_INSTRUCTION_LEAK_MARKERS = (
    "system prompt",
    "hidden instruction",
    "developer instruction",
)

_LOCATION_RE = re.compile(r"(?:^|\b)location\s*:\s*([^\n|]+)", re.IGNORECASE)
_STATUS_RE = re.compile(r"(?:^|\b)status\s*:\s*([^\n|]+)", re.IGNORECASE)
_CLIENT_RE = re.compile(r"(?:^|\b)client\s*:\s*([^\n|]+)", re.IGNORECASE)
_SIZE_RE = re.compile(
    r"((?:built[\s\-]*up\s+area|area)(?:\s*[:\-]|\s+of)?\s*[\d,.\s]+(?:sq\.?\s*ft|sqft|sqm|sq\.?\s*m))",
    re.IGNORECASE,
)
_NAV_TEXT_RE = re.compile(r"\b(projects?|home|contact us|services?)\b", re.IGNORECASE)
_GENERIC_TITLE_RE = re.compile(r"^(obe|projects?)$", re.IGNORECASE)
_PROJECT_DETAIL_RE = re.compile(r"project-detail\.php\?id=\d+", re.IGNORECASE)
_PROJECT_ID_RE = re.compile(r"(?:project-detail\.php\?id=|project\s*#?\s*)(\d+)", re.IGNORECASE)
_FLOORS_RE = re.compile(r"(?:number of floors|floors?)\s*[:\-]\s*([^\n|.;]{1,30})", re.IGNORECASE)
_DESIGN_STYLE_RE = re.compile(r"(?:design style|style)\s*[:\-]\s*([^\n|.;]{2,120})", re.IGNORECASE)
_FEATURES_RE = re.compile(r"(?:features?)\s*[:\-]\s*([^\n|.]{2,180})", re.IGNORECASE)
_SPACES_RE = re.compile(r"(?:typical spaces?)\s*[:\-]\s*([^\n|.]{2,180})", re.IGNORECASE)
_MATERIALS_RE = re.compile(r"(?:materials?|fa.?ade|facade)\s*[:\-]\s*([^\n|.]{2,180})", re.IGNORECASE)
_SITE_CONTEXT_RE = re.compile(r"(?:site context)\s*[:\-]\s*([^\n|.]{2,180})", re.IGNORECASE)
_FOLLOW_UP_STOPWORDS = {
    "the", "is", "are", "and", "or", "about", "more", "information",
    "provide", "please", "what", "which", "where", "when", "who", "why",
    "how", "a", "an", "to", "in", "of", "for", "on", "with", "from",
    "these", "this", "that", "it", "its", "be", "as", "by", "at", "do",
    "does", "can", "you", "we", "our", "their", "there",
}

ROUTE_CATEGORY_OVERVIEW = "category_overview"
ROUTE_CATEGORY_DEEP_DIVE = "category_deep_dive"
ROUTE_PROJECT_DETAIL = "project_detail"
ROUTE_GUIDED_FLOW = "guided_flow"
ROUTE_GENERAL_RAG = "general_rag"

_CATEGORY_CONFIG: dict[str, dict[str, Any]] = {
    "villas": {
        "title": "Villas Designed by OBE Architects",
        "keywords": ["villas", "villa projects", "residential villas"],
    },
    "commercial": {
        "title": "Commercial Projects by OBE Architects",
        "keywords": ["commercial", "retail", "business center", "office"],
    },
    "sports": {
        "title": "Sports Facilities Designed by OBE Architects",
        "keywords": ["sports", "sport", "stadium", "club", "fitness"],
    },
    "education": {
        "title": "Education Projects by OBE Architects",
        "keywords": ["education", "educational", "school", "college", "university"],
    },
    "mosques": {
        "title": "Mosques Designed by OBE Architects",
        "keywords": ["mosque", "mosques", "masjid"],
    },
    "public-and-cultural": {
        "title": "Public & Cultural Projects by OBE Architects",
        "keywords": ["public", "cultural", "culture", "civic"],
    },
    "public_cultural": {
        "title": "Public & Cultural Projects by OBE Architects",
        "keywords": ["public", "cultural", "culture", "civic"],
    },
}

_CATEGORY_FOLLOW_UPS_TEXT: dict[str, list[str]] = {
    "villas": [
        "Can you provide more information about the exterior design features?",
        "Can you elaborate on materials and facade treatments used in these villas?",
        "Can you describe the architectural style or design approach mentioned for these villas?",
    ],
    "commercial": [
        "Can you provide more details about the project components and layout?",
        "Can you describe the scale and built-up areas where available?",
        "Can you elaborate on materials and facade treatments mentioned for these commercial projects?",
    ],
    "sports": [
        "Can you elaborate on spatial organization and functional zones mentioned?",
        "Can you describe the architectural style or design approach mentioned for these sports facilities?",
        "Can you describe the scale and built-up areas where available?",
    ],
    "education": [
        "Can you describe the academic and support facilities included?",
        "Can you describe the scale and built-up areas where available?",
        "Can you provide more details about architectural style and design approach?",
    ],
    "mosques": [
        "Can you elaborate on prayer hall and supporting spaces mentioned?",
        "Can you describe the scale and built-up areas where available?",
        "Can you describe the architectural style or design approach mentioned for these mosques?",
    ],
    "public-and-cultural": [
        "Can you describe the architectural style or design approach mentioned for these projects?",
        "Can you provide more information about spatial organization and public areas?",
        "Can you elaborate on materials or facade treatments mentioned for these projects?",
    ],
    "public_cultural": [
        "Can you describe the architectural style or design approach mentioned for these projects?",
        "Can you provide more information about spatial organization and public areas?",
        "Can you elaborate on materials or facade treatments mentioned for these projects?",
    ],
}


@dataclass
class RagAnswerResult:
    answer: str
    sources: list[dict[str, str | None]]
    confidence: float
    follow_up_buttons: list[str] = field(default_factory=list)
    route_taken: str = "rag"
    route_kind: str = ROUTE_GENERAL_RAG
    category_slug: str | None = None
    retrieval_top_score: float | None = None
    retrieval_k: int | None = None
    fallback_reason: str | None = None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _normalize_confidence(matches: list[dict[str, Any]]) -> float:
    if not matches:
        return 0.0
    return _clamp(float(matches[0].get("score") or 0.0))


def _stable_sort_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        matches,
        key=lambda item: (
            -float(item.get("score") or 0.0),
            int(item.get("chunk_id") or 0),
            str(item.get("url") or ""),
            str(item.get("chunk_text") or ""),
        ),
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_category(text: str) -> str | None:
    normalized = _normalize_for_match(text)
    if not normalized:
        return None
    if _PROJECT_ID_RE.search(normalized):
        return None

    category_aliases: list[tuple[str, str]] = [
        ("public and cultural", "public-and-cultural"),
        ("public & cultural", "public-and-cultural"),
        ("public cultural", "public-and-cultural"),
        ("culture", "public-and-cultural"),
        ("commercial projects", "commercial"),
        ("commercial", "commercial"),
        ("sports", "sports"),
        ("sport", "sports"),
        ("stadium", "sports"),
        ("education projects", "education"),
        ("education", "education"),
        ("school", "education"),
        ("university", "education"),
        ("mosques", "mosques"),
        ("mosque", "mosques"),
        ("villa projects", "villas"),
        ("villas", "villas"),
        ("villa", "villas"),
    ]
    for alias, slug in category_aliases:
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            # Treat "Court Villa" style asks as project-detail rather than category overview.
            if (
                slug == "villas"
                and "villa" in normalized
                and "villas" not in normalized
                and "projects" not in normalized
            ):
                if re.search(r"\b(?:tell me more about|details? about|about)\s+[a-z]+\s+villa\b", normalized):
                    return None
            return slug
    return None


def _detect_category_slug(question: str) -> str | None:
    return normalize_category(question)


def detect_category_deep_dive(question: str) -> str | None:
    normalized = _normalize_for_match(question)
    if not normalized:
        return None
    if re.search(r"\bmaterials?\b", normalized):
        return "materials"
    if re.search(r"\b(exterior|facade|elevation)\b", normalized):
        return "exterior"
    if re.search(r"\b(features?|design features?)\b", normalized):
        return "features"
    if re.search(r"\b(spaces?|interior|outdoor|layout|components?|program)\b", normalized):
        return "spaces"
    if re.search(r"\b(style|architectural style|design approach)\b", normalized):
        return "style"
    if re.search(r"\b(area|built[\s\-]*up|builtup|bua|size|scale|sqm|m2|sq\.?\s*m|sq\.?\s*ft)\b", normalized):
        return "scale"
    return None


def _extract_explicit_project_id(text: str) -> str | None:
    if not text:
        return None
    match = _PROJECT_ID_RE.search(text)
    if match and match.group(1).isdigit():
        return match.group(1)
    return None


def _extract_project_phrase(question: str) -> str | None:
    if not question:
        return None
    matches = re.findall(r"\b[A-Z][a-z]+(?:[\s&\\-][A-Z][a-z]+)+\b", question)
    if not matches:
        return None
    return max(matches, key=len).strip()


def _row_to_match(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": int(row.get("chunk_id") or 0),
        "url": row.get("url") or "",
        "title": row.get("title") or "",
        "doc_type": row.get("doc_type") or "",
        "chunk_text": row.get("chunk_text") or "",
        "score": float(row.get("score") or 0.0),
    }


def _retrieve_keyword_matches(phrase: str, top_k: int) -> list[dict[str, Any]]:
    if not phrase:
        return []
    pattern = f"%{phrase}%"
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  rc.id AS chunk_id,
                  rc.chunk_text,
                  rc.document_url AS url,
                  rd.title,
                  rd.doc_type,
                  1.0 AS score
                FROM rag_chunks rc
                JOIN rag_documents rd ON rd.url = rc.document_url
                WHERE rc.chunk_text ILIKE %s
                   OR rd.title ILIKE %s
                   OR rc.document_url ILIKE %s
                ORDER BY rc.id ASC
                LIMIT %s
                """,
                (pattern, pattern, pattern, top_k),
            )
            rows = cur.fetchall()
    return [_row_to_match(row) for row in rows]


def _is_explicit_project_request(question: str, context_urls: list[str] | None) -> bool:
    normalized = _normalize_for_match(question)
    if not normalized:
        return False
    if _PROJECT_DETAIL_RE.search(question) or _PROJECT_ID_RE.search(question):
        return True
    if context_urls and re.search(r"\b(?:this project|that project|tell me more|details?)\b", normalized):
        return True
    if re.search(r"\btell me more about [A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,}\b", question or ""):
        return True
    if re.search(r"\b(?:information about|details about|more information about|provide more information about)\b", normalized):
        if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,}\b", question or ""):
            return True
    return False


def _is_guided_lead_flow(question: str, context_urls: list[str] | None) -> bool:
    normalized = _normalize_for_match(question)
    if not normalized or context_urls:
        return False
    return bool(
        re.search(
            r"\b(?:consultation|quote|budget|contact me|call me|phone|email|visit|appointment|lead)\b",
            normalized,
        )
    )


def _resolve_route(question: str, context_urls: list[str] | None) -> tuple[str, str | None]:
    category_slug = _detect_category_slug(question)
    if category_slug:
        return ROUTE_CATEGORY_OVERVIEW, category_slug
    if _is_explicit_project_request(question, context_urls):
        return ROUTE_PROJECT_DETAIL, None
    if _is_guided_lead_flow(question, context_urls):
        return ROUTE_GUIDED_FLOW, None
    return ROUTE_GENERAL_RAG, None


def _category_title(category_slug: str) -> str:
    config = _CATEGORY_CONFIG.get(category_slug) or _CATEGORY_CONFIG.get(category_slug.replace("-", "_")) or {}
    title = str(config.get("title") or "").strip()
    if title:
        return title
    human = category_slug.replace("-", " ").replace("_", " ").title()
    return f"{human} Designed by OBE Architects"


def _category_short_name(category_slug: str) -> str:
    title = _category_title(category_slug)
    title = re.sub(r"\s+Designed by OBE Architects\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+by OBE Architects\s*$", "", title, flags=re.IGNORECASE)
    return title.strip() or category_slug.replace("-", " ").replace("_", " ").title()


def _deep_dive_title(topic: str, category_slug: str) -> str:
    topic_map = {
        "exterior": "Exterior Design Features",
        "materials": "Materials and Facade Treatments",
        "features": "Design Features",
        "spaces": "Project Components and Layout",
        "style": "Architectural Style and Design Approach",
        "scale": "Scale and Built-up Areas",
    }
    topic_title = topic_map.get(topic, "Design Details")
    return f"{topic_title} of OBE Architects' {_category_short_name(category_slug)}"


def _infer_category_from_context_urls(context_urls: list[str] | None) -> str | None:
    if not context_urls:
        return None
    for slug in _CATEGORY_CONFIG:
        aliases = _category_url_aliases(slug)
        for url in context_urls:
            url_lower = str(url or "").lower()
            if any(f"category={alias}" in url_lower for alias in aliases):
                return slug
            if any(alias in url_lower for alias in aliases):
                return slug
    # Fallback: inspect the context URLs' chunk text for category keywords.
    try:
        matches = _stable_sort_matches(
            retrieve_chunks(
                query="category context",
                top_k=8,
                min_score=0.0,
                url_filters=context_urls,
            )
        )
    except Exception:
        return None

    if not matches:
        return None

    scores: dict[str, int] = {slug: 0 for slug in _CATEGORY_CONFIG}
    for item in matches:
        for slug in _CATEGORY_CONFIG:
            if _match_is_category_relevant(item, slug):
                scores[slug] += 1
    best_slug = max(scores.items(), key=lambda item: item[1])[0]
    return best_slug if scores.get(best_slug, 0) > 0 else None
    return None


def _category_keywords(category_slug: str) -> list[str]:
    config = _CATEGORY_CONFIG.get(category_slug) or _CATEGORY_CONFIG.get(category_slug.replace("-", "_")) or {}
    keywords = [str(keyword).lower() for keyword in config.get("keywords", []) if str(keyword).strip()]
    if category_slug == "villas":
        keywords.extend(["villa", "residential villa"])
    return keywords


def _category_url_aliases(category_slug: str) -> list[str]:
    aliases = [category_slug]
    if category_slug == "public-and-cultural":
        aliases.extend(["publicncultural", "public_cultural"])
    return aliases


def _normalize_meta_value(value: str) -> str | None:
    clean = _clean_text(value)
    if not clean:
        return None
    clean = clean.strip(" -|,.;")
    return clean or None


def _project_fallback_title(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.path.endswith("project-detail.php"):
            project_id = parse_qs(parsed.query).get("id", [""])[0].strip()
            if project_id.isdigit():
                return f"OBE Project #{project_id}"
    except Exception:
        return "OBE Project"
    return "OBE Project"


def _extract_title(chunk_text: str, fallback: str) -> str:
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", chunk_text or "") if ln.strip()]
    for line in lines[:8]:
        if len(line) < 3:
            continue
        if _LOCATION_RE.search(line) or _STATUS_RE.search(line):
            continue
        if _NAV_TEXT_RE.fullmatch(line):
            continue
        return _clean_text(line[:110])
    return fallback


def _extract_labeled_value(chunk_text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"{label}\s*:\s*(.+?)(?=(?:\b(?:client|location|status|built[\s\-]*up\s+area|area)\s*:)|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(chunk_text or "")
    if not match:
        return None
    return _normalize_meta_value(match.group(1))


def _extract_location(chunk_text: str) -> str | None:
    value = _extract_labeled_value(chunk_text, "location")
    if not value:
        return None
    # Keep short place names only.
    value = re.split(r"\s+(?:status|client|built[\s\-]*up|area)\s*:", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(r"\s{2,}|[.;]", value, maxsplit=1)[0]
    return _normalize_meta_value(value)


def _extract_status(chunk_text: str) -> str | None:
    value = _extract_labeled_value(chunk_text, "status")
    if not value:
        return None
    value = re.split(r"\s+(?:location|client|built[\s\-]*up|area)\s*:", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+The\s+", value, maxsplit=1)[0]
    value = re.split(r"[.;]", value, maxsplit=1)[0]
    words = value.split()
    if not words:
        return None
    return _normalize_meta_value(" ".join(words[:3]))


def _extract_size(chunk_text: str) -> str | None:
    labeled = _extract_labeled_value(chunk_text, r"(?:built[\s\-]*up\s+area|area)")
    if labeled:
        value_match = re.search(
            r"[\d,.\s]+(?:sq\.?\s*ft|sqft|sqm|sq\.?\s*m)",
            labeled,
            flags=re.IGNORECASE,
        )
        if value_match:
            value = _normalize_meta_value(value_match.group(0))
            if not value:
                return None
            return re.sub(r"^of\s+", "", value, flags=re.IGNORECASE)

    match = _SIZE_RE.search(chunk_text or "")
    if not match:
        return None
    value = _normalize_meta_value(match.group(1))
    if not value:
        return None
    value = re.sub(r"^(?:built[\s\-]*up\s+area|area)(?:\s*[:\-]|\s+of)?\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"^of\s+", "", value, flags=re.IGNORECASE)


def _strip_inline_labeled_segments(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"client\s*:\s*[A-Za-z][A-Za-z\s&/-]{0,32}",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"location\s*:\s*[A-Za-z][A-Za-z\s&/-]{0,32}",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"status\s*:\s*[A-Za-z][A-Za-z\s&/-]{0,20}",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?:built[\s\-]*up\s+area|area)(?:\s*[:\-]|\s+of)?\s*[\d,.\s]+(?:sq\.?\s*ft|sqft|sqm|sq\.?\s*m)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _is_generic_overview(text: str) -> bool:
    lowered = text.lower()
    generic_markers = {
        "obe project",
        "project overview",
        "projects",
        "project",
    }
    return lowered in generic_markers


def _clean_overview_candidate(text: str, title: str) -> str:
    candidate = _clean_text(text)
    if title:
        escaped_title = re.escape(title)
        candidate = re.sub(rf"^(?:projects?\s+)?{escaped_title}\b[:\-]?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^projects?\b[:\-]?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*:\s*", " ", candidate)
    candidate = _clean_text(candidate)
    return candidate


def _split_sentences(text: str) -> list[str]:
    raw_parts = re.split(r"(?<=[.!?])\s+", _clean_text(text))
    out: list[str] = []
    for part in raw_parts:
        sentence = part.strip().strip(". ")
        if not sentence:
            continue
        sentence = re.sub(r"\.{2,}$", "", sentence).strip()
        if not sentence:
            continue
        out.append(f"{sentence}.")
    return out


def _finalize_overview(text: str, max_len: int = 220) -> str | None:
    cleaned = _clean_text(text).rstrip(". ").strip()
    cleaned = re.sub(r"\.{2,}$", "", cleaned).strip()
    if not cleaned:
        return None

    sentences = _split_sentences(cleaned)
    if sentences:
        picked: list[str] = []
        total_len = 0
        for sentence in sentences:
            next_len = total_len + len(sentence) + (1 if picked else 0)
            if next_len > max_len:
                break
            picked.append(sentence)
            total_len = next_len
            if len(picked) >= 2:
                break
        if picked:
            return " ".join(picked)

        # If the first sentence alone exceeds max_len, shorten by whole words and end cleanly.
        first = sentences[0]
        shortened = first[:max_len].rsplit(" ", 1)[0].strip()
        shortened = shortened.strip(". ").strip()
        if shortened:
            return f"{shortened}."
        return None

    # No clear sentence punctuation found; convert to one clean sentence.
    clipped = cleaned[:max_len].rsplit(" ", 1)[0].strip() if len(cleaned) > max_len else cleaned
    clipped = clipped.strip(". ").strip()
    if not clipped:
        return None
    return f"{clipped}."


def _extract_overview(chunk_text: str, title: str) -> str | None:
    if not chunk_text:
        return None
    kept_lines: list[str] = []
    for raw_line in re.split(r"[\r\n]+", chunk_text):
        line = raw_line.strip()
        if not line:
            continue
        line = _strip_inline_labeled_segments(line)
        line = _clean_overview_candidate(line, title)
        if not line:
            continue
        if line.lower() in {"projects", "project", "obe", "home"}:
            continue
        kept_lines.append(line)

    cleaned = _clean_text(" ".join(kept_lines))
    if not cleaned or _NAV_TEXT_RE.fullmatch(cleaned):
        return None

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if not sentences:
        sentences = [cleaned]

    picked: list[str] = []
    total_len = 0
    for sentence in sentences:
        sentence = _clean_overview_candidate(sentence, title)
        if not sentence:
            continue
        if re.search(r"\b(client|location|status|built[\s\-]*up|area)\s*:", sentence, flags=re.IGNORECASE):
            continue
        if _is_generic_overview(sentence):
            continue
        next_len = total_len + len(sentence) + (1 if picked else 0)
        if next_len > 160:
            break
        picked.append(sentence)
        total_len = next_len
        if len(picked) >= 2:
            break

    if not picked:
        fallback = _clean_overview_candidate(cleaned, title)
        if not fallback or _is_generic_overview(fallback):
            return None
        return _finalize_overview(fallback, max_len=220)

    return _finalize_overview(_clean_text(" ".join(picked)), max_len=220)


def _build_source_item(item: dict[str, Any]) -> dict[str, str | None]:
    url = str(item.get("url") or "").strip()
    chunk_text = str(item.get("chunk_text") or "")
    title = _clean_text(str(item.get("title") or ""))

    if not title or _GENERIC_TITLE_RE.fullmatch(title):
        title = _extract_title(chunk_text, _project_fallback_title(url))

    return {
        "url": url,
        "title": title,
        "doc_type": _clean_text(str(item.get("doc_type") or "")).lower() or None,
        "location": _extract_location(chunk_text),
        "status": _extract_status(chunk_text),
        "size": _extract_size(chunk_text),
        "overview": _extract_overview(chunk_text, title),
    }


def _merge_sources(
    existing: dict[str, str | None],
    incoming: dict[str, str | None],
) -> dict[str, str | None]:
    merged = dict(existing)
    if (
        (not merged.get("title") or str(merged["title"]) in {"Source", "OBE Project"})
        and incoming.get("title")
    ):
        merged["title"] = incoming["title"]

    for field in ("location", "status", "size"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]
    if not merged.get("doc_type") and incoming.get("doc_type"):
        merged["doc_type"] = incoming["doc_type"]

    current_overview = str(merged.get("overview") or "")
    incoming_overview = str(incoming.get("overview") or "")
    if len(incoming_overview) > len(current_overview):
        merged["overview"] = incoming_overview
    return merged


def _normalize_sources(sources: Sequence[Any]) -> list[dict[str, str | None]]:
    deduped: dict[str, dict[str, str | None]] = {}

    for source in sources:
        item: dict[str, str | None]
        if isinstance(source, str):
            url = source.strip()
            if not url:
                continue
            item = {
                "url": url,
                "title": "Source",
                "location": None,
                "status": None,
                "size": None,
                "overview": None,
            }
        elif isinstance(source, dict):
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            item = {
                "url": url,
                "title": _clean_text(str(source.get("title") or "")) or _project_fallback_title(url),
                "location": _normalize_meta_value(str(source.get("location") or "")),
                "status": _normalize_meta_value(str(source.get("status") or "")),
                "size": _normalize_meta_value(str(source.get("size") or "")),
                "overview": (
                    _finalize_overview(
                        str(
                            source.get("overview")
                            or source.get("blurb")
                            or source.get("summary")
                            or source.get("chunk_text")
                            or ""
                        ),
                        max_len=220,
                    )
                    or None
                ),
            }
        else:
            continue

        url_key = item.get("url")
        if not url_key:
            continue
        existing = deduped.get(url_key)
        deduped[url_key] = _merge_sources(existing, item) if existing else item

    return list(deduped.values())


def _build_context(
    matches: list[dict[str, Any]],
    max_chars: int,
) -> tuple[str, list[dict[str, str | None]]]:
    parts: list[str] = []
    sources: list[dict[str, str | None]] = []
    total_chars = 0

    for item in matches:
        url = str(item.get("url") or "").strip()
        chunk_text = str(item.get("chunk_text") or "").strip()
        if not url or not chunk_text:
            continue

        block = f"[SOURCE] {url}\n{chunk_text}\n\n"
        if total_chars + len(block) > max_chars:
            break

        parts.append(block)
        total_chars += len(block)
        sources.append(_build_source_item(item))

    return "".join(parts).strip(), sources


def _is_project_source(source: dict[str, Any] | dict[str, str | None] | str) -> bool:
    if isinstance(source, str):
        return bool(_PROJECT_DETAIL_RE.search(source or ""))

    url = str(source.get("url") or "").strip()
    doc_type = _clean_text(str(source.get("doc_type") or "")).lower()
    return bool(_PROJECT_DETAIL_RE.search(url)) or doc_type == "project"


def _filter_project_sources(
    sources: Sequence[dict[str, Any] | dict[str, str | None] | str],
) -> list[dict[str, Any] | dict[str, str | None] | str]:
    return [source for source in sources if _is_project_source(source)]


def _strip_internal_source_fields(sources: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    cleaned: list[dict[str, str | None]] = []
    for source in sources:
        item = dict(source)
        item.pop("doc_type", None)
        cleaned.append(item)
    return cleaned


def _match_is_category_relevant(item: dict[str, Any], category_slug: str) -> bool:
    keywords = _category_keywords(category_slug)
    if not keywords:
        return False
    blob = _normalize_for_match(
        " ".join(
            [
                str(item.get("url") or ""),
                str(item.get("title") or ""),
                str(item.get("doc_type") or ""),
                str(item.get("chunk_text") or ""),
            ]
        )
    )
    return any(keyword in blob for keyword in keywords)


def _prioritize_category_matches(matches: list[dict[str, Any]], category_slug: str, top_k: int) -> list[dict[str, Any]]:
    if not category_slug:
        return _stable_sort_matches(matches)

    preferred = [item for item in matches if _match_is_category_relevant(item, category_slug)]
    if not preferred:
        # Fallback to base retrieval order when strict keyword/category hints are absent.
        return _stable_sort_matches(matches)[:top_k]

    return _stable_sort_matches(preferred)[:top_k]


def _extract_follow_up_line(text: str) -> tuple[str, str | None]:
    lines = text.split("\n")
    follow_up: str | None = None
    kept: list[str] = []

    for line in lines:
        match = re.match(r"^\s*follow-up question:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            if follow_up is None:
                follow_up = _clean_text(match.group(1))
            continue
        kept.append(line)

    body = "\n".join(kept).strip()
    return body, follow_up


def _normalize_for_match(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_significant_tokens(text: str) -> list[str]:
    normalized = _normalize_for_match(text)
    tokens = [tok for tok in normalized.split() if tok not in _FOLLOW_UP_STOPWORDS and len(tok) >= 3]
    return tokens


def _build_followup_grounding_text(
    context_text: str,
    sources: list[dict[str, str | None]],
) -> str:
    parts = [context_text or ""]
    for src in sources:
        parts.extend([
            str(src.get("title") or ""),
            str(src.get("location") or ""),
            str(src.get("status") or ""),
            str(src.get("size") or ""),
            str(src.get("overview") or ""),
        ])
    return _normalize_for_match(" ".join(parts))


def _safe_follow_up_from_sources(sources: list[dict[str, str | None]]) -> str | None:
    if any(str(src.get("size") or "").strip() for src in sources):
        return "Which project has the largest built-up area in these sources?"

    if any(str(src.get("status") or "").strip() for src in sources):
        return "Which projects in these sources are marked as completed?"

    locations = [str(src.get("location") or "").strip() for src in sources if str(src.get("location") or "").strip()]
    if locations:
        return f"Which projects in these sources are located in {locations[0]}?"

    return None


def _pick_category_follow_up(
    category_slug: str,
    sources: list[dict[str, str | None]],
    seed_key: str | None = None,
) -> str | None:
    templates = _CATEGORY_FOLLOW_UPS_TEXT.get(category_slug) or []
    if not templates:
        return _safe_follow_up_from_sources(sources)
    base = seed_key or category_slug
    seed_text = base + "|" + category_slug + "|" + "|".join(sorted({str(src.get("url") or "") for src in sources}))
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest(), 16)
    return templates[seed % len(templates)]


def _validate_or_replace_follow_up(
    follow_up: str | None,
    context_text: str,
    sources: list[dict[str, str | None]],
) -> str | None:
    if not follow_up:
        return None

    normalized_follow_up = _normalize_for_match(follow_up)
    if not normalized_follow_up:
        return None

    if " and " in normalized_follow_up or " or " in normalized_follow_up:
        return _safe_follow_up_from_sources(sources)

    words = normalized_follow_up.split()
    if len(words) < 8 or len(words) > 14:
        return _safe_follow_up_from_sources(sources)

    tokens = _extract_significant_tokens(follow_up)
    if not tokens:
        return _safe_follow_up_from_sources(sources)

    grounding_text = _build_followup_grounding_text(context_text, sources)
    token_matches = sum(1 for token in tokens if token in grounding_text)
    min_required = 1 if len(tokens) <= 2 else 2
    if token_matches < min_required:
        return _safe_follow_up_from_sources(sources)

    return follow_up


def _safe_follow_up_candidates(sources: list[dict[str, str | None]]) -> list[str]:
    candidates: list[str] = []
    if any(str(src.get("size") or "").strip() for src in sources):
        candidates.append("Which project has the largest built-up area in these sources?")
    if any(str(src.get("status") or "").strip() for src in sources):
        candidates.append("Which projects in these sources are marked as completed?")
    locations = [str(src.get("location") or "").strip() for src in sources if str(src.get("location") or "").strip()]
    if locations:
        candidates.append(f"Which projects in these sources are located in {locations[0]}?")
    return candidates


def _extract_follow_up_questions(answer: str) -> list[str]:
    lines = [line.rstrip() for line in (answer or "").splitlines()]
    collected: list[str] = []
    in_section = False
    for raw in lines:
        line = raw.strip()
        if not line:
            if in_section:
                break
            continue
        if re.match(r"^follow-up questions?:", line, flags=re.IGNORECASE):
            in_section = True
            single = re.sub(r"^follow-up questions?:\s*", "", line, flags=re.IGNORECASE).strip()
            if single:
                collected.append(single)
            continue
        if in_section:
            if line.startswith("- ") or line.startswith("* ") or line.startswith("• ") or line.startswith("â€¢ "):
                collected.append(re.sub(r"^\s*(?:[-*]|•|â€¢)\s*", "", line).strip())
                continue
            break
        if re.match(r"^follow-up question:", line, flags=re.IGNORECASE):
            collected.append(re.sub(r"^follow-up question:\s*", "", line, flags=re.IGNORECASE).strip())
    return [q for q in collected if q]


def _strip_follow_up_section(answer: str) -> str:
    lines = [line.rstrip() for line in (answer or "").splitlines()]
    out: list[str] = []
    skip = False
    for raw in lines:
        line = raw.strip()
        if re.match(r"^follow-up questions?:", line, flags=re.IGNORECASE):
            skip = True
            continue
        if skip:
            if line.startswith("- ") or line.startswith("* ") or line.startswith("• ") or line.startswith("â€¢ "):
                continue
            if not line:
                continue
            skip = False
        if re.match(r"^follow-up question:", line, flags=re.IGNORECASE):
            continue
        out.append(raw)
    return "\n".join(out).strip()


def _validate_or_replace_follow_ups(
    follow_ups: list[str],
    context_text: str,
    sources: list[dict[str, str | None]],
) -> list[str]:
    vetted: list[str] = []
    seen: set[str] = set()
    for follow_up in follow_ups:
        candidate = _validate_or_replace_follow_up(follow_up, context_text, sources)
        if not candidate:
            continue
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        vetted.append(normalized)
        if len(vetted) >= 4:
            break

    if len(vetted) < 3:
        for fallback in _safe_follow_up_candidates(sources):
            if fallback in seen:
                continue
            vetted.append(fallback)
            seen.add(fallback)
            if len(vetted) >= 3:
                break

    return vetted[:4]


def _collect_unique(values: list[str], limit: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        clean = _clean_text(raw)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _extract_numeric_area(size_text: str) -> tuple[float | None, str | None]:
    match = re.search(r"([\d,.]+)\s*(sq\.?\s*ft|sqft|sqm|sq\.?\s*m)", size_text or "", flags=re.IGNORECASE)
    if not match:
        return None, None
    raw_value = match.group(1).replace(",", "").strip()
    try:
        value = float(raw_value)
    except Exception:
        return None, None
    unit = _clean_text(match.group(2)).lower().replace("  ", " ")
    return value, unit


def _extract_optional_labeled_value(chunk_text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(chunk_text or "")
    if not match:
        return None
    return _normalize_meta_value(match.group(1))


def _extract_category_highlights(matches: list[dict[str, Any]], sources: list[dict[str, str | None]], min_occurrences: int = 2) -> list[tuple[str, str]]:
    highlights: list[tuple[str, str]] = []

    area_values: list[tuple[float, str]] = []
    area_has_up_to_phrase = False
    for src in sources:
        size_text = str(src.get("size") or "").strip()
        if not size_text:
            continue
        numeric, unit = _extract_numeric_area(size_text)
        if numeric is None or not unit:
            continue
        area_values.append((numeric, unit))

    for item in matches:
        chunk_text = str(item.get("chunk_text") or "")
        if re.search(r"\bup to\b", chunk_text, flags=re.IGNORECASE):
            area_has_up_to_phrase = True

    if len(area_values) >= 2:
        by_unit: dict[str, list[float]] = {}
        for value, unit in area_values:
            by_unit.setdefault(unit, []).append(value)
        biggest_unit = max(by_unit.items(), key=lambda item: len(item[1]))[0]
        values = sorted(by_unit[biggest_unit])
        if len(values) >= 2:
            unit_label = biggest_unit.replace("sqft", "sq.ft").replace("sq ft", "sq.ft").replace("sq. m", "sqm")
            lo = int(values[0]) if values[0].is_integer() else values[0]
            hi = int(values[-1]) if values[-1].is_integer() else values[-1]
            highlights.append(("Built-up areas", f"Range from {lo:,} {unit_label} to {hi:,} {unit_label}."))
    elif len(area_values) == 1:
        only_value, only_unit = area_values[0]
        val = int(only_value) if only_value.is_integer() else only_value
        unit_label = only_unit.replace("sqft", "sq.ft").replace("sq ft", "sq.ft").replace("sq. m", "sqm")
        if area_has_up_to_phrase:
            highlights.append(("Built-up areas", f"Up to {val:,} {unit_label}."))
        else:
            highlights.append(("Built-up areas", f"Around {val:,} {unit_label}."))

    location_counts: dict[str, int] = {}
    for src in sources:
        location = str(src.get("location") or "").strip()
        if not location:
            continue
        location_counts[location] = location_counts.get(location, 0) + 1
    if location_counts:
        ranked = sorted(location_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        top_location, top_count = ranked[0]
        total = sum(location_counts.values())
        if total >= 2 and top_count > (total / 2):
            highlights.append(("Location", f"Mostly {top_location}."))
        elif len(ranked) > 1:
            highlights.append(("Location", ", ".join(location for location, _count in ranked[:3]) + "."))
        else:
            highlights.append(("Location", f"{top_location}."))
    statuses = _collect_unique([str(src.get("status") or "") for src in sources], limit=4)
    if statuses:
        status_text = ", ".join(statuses[:3])
        highlights.append(("Status", f"{status_text}."))

    floor_values: list[str] = []
    style_values: list[str] = []
    feature_values: list[str] = []
    space_values: list[str] = []
    material_values: list[str] = []
    context_values: list[str] = []

    for item in matches:
        chunk_text = str(item.get("chunk_text") or "")
        floor = _extract_optional_labeled_value(chunk_text, _FLOORS_RE)
        style = _extract_optional_labeled_value(chunk_text, _DESIGN_STYLE_RE)
        feature = _extract_optional_labeled_value(chunk_text, _FEATURES_RE)
        space = _extract_optional_labeled_value(chunk_text, _SPACES_RE)
        material = _extract_optional_labeled_value(chunk_text, _MATERIALS_RE)
        context = _extract_optional_labeled_value(chunk_text, _SITE_CONTEXT_RE)
        if floor:
            floor_values.append(floor)
        if style:
            style_values.append(style)
        if feature:
            feature_values.append(feature)
        if space:
            space_values.append(space)
        if material:
            material_values.append(material)
        if context:
            context_values.append(context)

    optional_map = [
        ("Number of floors", floor_values),
        ("Design style", style_values),
        ("Features", feature_values),
        ("Typical spaces", space_values),
        ("Materials / facade", material_values),
        ("Site context", context_values),
    ]
    for label, values in optional_map:
        value_counts: dict[str, int] = {}
        for raw in values:
            clean = _clean_text(raw)
            if not clean:
                continue
            value_counts[clean] = value_counts.get(clean, 0) + 1
        recurring = [value for value, count in value_counts.items() if count >= min_occurrences]
        unique_values = _collect_unique(recurring, limit=2)
        if not unique_values:
            continue
        combined = "; ".join(unique_values) + "."
        highlights.append((label, combined))

    return highlights[:6]


def _format_category_overview_answer(
    category_slug: str,
    matches: list[dict[str, Any]],
    sources: list[dict[str, str | None]],
    related_projects: list[dict[str, str | None]] | None = None,
    follow_up: str | None = None,
    follow_up_questions: list[str] | None = None,
) -> str:
    title = _category_title(category_slug)
    highlights = _extract_category_highlights(matches=matches, sources=sources, min_occurrences=1)
    if not highlights:
        snippets = _extract_overview_snippets(matches, limit=3)
        highlights = [(title, text) for title, text in snippets]
    return _format_structured_answer(
        title=title,
        highlights=highlights,
        related_projects=related_projects or [],
        follow_up=follow_up,
        follow_up_questions=follow_up_questions,
        include_related_projects=False,
        include_follow_up=False,
    )


def _combine_unique(values: list[str], limit: int = 3) -> str | None:
    unique_values = _collect_unique(values, limit=limit)
    if not unique_values:
        return None
    return "; ".join(unique_values) + "."


def _extract_keyword_snippets(
    matches: list[dict[str, Any]],
    keyword_pattern: re.Pattern[str],
    limit: int = 3,
) -> list[tuple[str, str]]:
    snippets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in matches:
        chunk_text = str(item.get("chunk_text") or "")
        if not chunk_text or not keyword_pattern.search(chunk_text):
            continue
        url = str(item.get("url") or "").strip()
        fallback_title = _project_fallback_title(url)
        title = _extract_title(chunk_text, fallback_title) or fallback_title
        for sentence in _split_sentences(chunk_text):
            if not keyword_pattern.search(sentence):
                continue
            clean = _clean_text(sentence)
            if not clean:
                continue
            dedupe_key = f"{title}|{clean}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            snippets.append((title, clean))
            if len(snippets) >= limit:
                return snippets
    return snippets


def _extract_overview_snippets(matches: list[dict[str, Any]], limit: int = 3) -> list[tuple[str, str]]:
    keyword_patterns = [
        re.compile(r"\b(school|college|university|campus|class|labs?|library|auditorium|gym|sports|hall)\b", re.I),
        re.compile(r"\b(mosque|prayer hall|minaret|ablution)\b", re.I),
        re.compile(r"\b(villa|residence|courtyard|pool|terrace|garden)\b", re.I),
        re.compile(r"\b(retail|shops?|f&b|food court|supermarket|office|commercial)\b", re.I),
        re.compile(r"\b(stadium|club|gym|arena|sports)\b", re.I),
        re.compile(r"\b(civic|public|cultural|museum|theater|gallery)\b", re.I),
    ]
    combined = re.compile("|".join(pattern.pattern for pattern in keyword_patterns), re.I)
    return _extract_keyword_snippets(matches, combined, limit=limit)


def _extract_deep_dive_highlights(
    topic: str,
    matches: list[dict[str, Any]],
    sources: list[dict[str, str | None]],
    context_text: str,
) -> list[tuple[str, str]]:
    highlights: list[tuple[str, str]] = []
    if topic == "scale":
        for label, value in _extract_category_highlights(matches=matches, sources=sources, min_occurrences=1):
            if label.lower() in {"built-up areas", "number of floors"}:
                highlights.append((label, value))
        highlights = _drop_unsupported_highlights(highlights, context_text=context_text, strict_text=True)[:6]
        if highlights:
            return highlights

    materials_values: list[str] = []
    features_values: list[str] = []
    style_values: list[str] = []
    spaces_values: list[str] = []
    context_values: list[str] = []

    for item in matches:
        chunk_text = str(item.get("chunk_text") or "")
        if topic in {"exterior", "features", "materials"}:
            material = _extract_optional_labeled_value(chunk_text, _MATERIALS_RE)
            feature = _extract_optional_labeled_value(chunk_text, _FEATURES_RE)
            style = _extract_optional_labeled_value(chunk_text, _DESIGN_STYLE_RE)
            if material:
                materials_values.append(material)
            if feature:
                features_values.append(feature)
            if style:
                style_values.append(style)
        if topic == "spaces":
            space = _extract_optional_labeled_value(chunk_text, _SPACES_RE)
            feature = _extract_optional_labeled_value(chunk_text, _FEATURES_RE)
            if space:
                spaces_values.append(space)
            if feature:
                features_values.append(feature)
        if topic == "style":
            style = _extract_optional_labeled_value(chunk_text, _DESIGN_STYLE_RE)
            context = _extract_optional_labeled_value(chunk_text, _SITE_CONTEXT_RE)
            if style:
                style_values.append(style)
            if context:
                context_values.append(context)

    if topic == "exterior":
        combined = [
            ("Materials / facade", _combine_unique(materials_values, limit=3)),
            ("Exterior features", _combine_unique(features_values, limit=3)),
            ("Design style", _combine_unique(style_values, limit=2)),
        ]
    elif topic == "materials":
        combined = [
            ("Materials / facade", _combine_unique(materials_values, limit=3)),
            ("Exterior features", _combine_unique(features_values, limit=2)),
            ("Design style", _combine_unique(style_values, limit=2)),
        ]
    elif topic == "features":
        combined = [
            ("Design features", _combine_unique(features_values, limit=3)),
            ("Materials / facade", _combine_unique(materials_values, limit=2)),
            ("Design style", _combine_unique(style_values, limit=2)),
        ]
    elif topic == "spaces":
        combined = [
            ("Typical spaces", _combine_unique(spaces_values, limit=3)),
            ("Key components", _combine_unique(features_values, limit=3)),
        ]
    elif topic == "style":
        combined = [
            ("Design style", _combine_unique(style_values, limit=3)),
            ("Site context", _combine_unique(context_values, limit=2)),
        ]
    else:
        combined = []

    for label, value in combined:
        if value:
            highlights.append((label, value))

    highlights = _drop_unsupported_highlights(highlights, context_text=context_text, strict_text=True)[:6]
    if highlights:
        return highlights

    topic_patterns = {
        "exterior": re.compile(r"\b(exterior|elevation|facade|façade|glass|window|pool|reflection)\b", re.I),
        "materials": re.compile(r"\b(materials?|stone|wood|glass|concrete|facade|façade)\b", re.I),
        "spaces": re.compile(r"\b(spaces?|layout|components?|ground floor|first floor|shops?|f&b|supermarket|food court|hall|prayer hall|classrooms?|labs?)\b", re.I),
        "style": re.compile(r"\b(style|modern|contemporary|classic|elegant|luxurious|concept|design approach)\b", re.I),
        "scale": re.compile(
            r"\b(built[\s\-]*up\s*area|builtup\s*area|bua|leasable area|gross floor|gfa)\b"
            r"|\\b\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?\\s*(sq\\.?\\s*ft|sqft|sqm|sq\\.?\\s*m|m2|square meters|square feet)\\b",
            re.I,
        ),
    }
    pattern = topic_patterns.get(topic)
    if not pattern:
        return []
    snippets = _extract_keyword_snippets(matches, pattern, limit=3)
    return [(title, snippet) for title, snippet in snippets]


def _format_category_deep_dive_answer(
    topic: str,
    category_slug: str,
    matches: list[dict[str, Any]],
    sources: list[dict[str, str | None]],
    context_text: str,
    related_projects: list[dict[str, str | None]] | None = None,
) -> str:
    title = _deep_dive_title(topic, category_slug)
    highlights = _extract_deep_dive_highlights(topic, matches, sources, context_text)
    if not highlights:
        highlights = [
            ("Summary", "The available portfolio text offers limited detail on this topic."),
            ("Coverage", "Share a specific project name for precise exterior, layout, or style details."),
            ("Note", "Only details explicitly mentioned in sources are included here."),
        ]
    return _format_structured_answer(
        title=title,
        highlights=highlights,
        related_projects=related_projects or [],
        include_related_projects=False,
        include_follow_up=False,
    )


def _format_structured_answer(
    title: str,
    highlights: list[tuple[str, str]],
    related_projects: list[dict[str, str | None]] | None = None,
    follow_up: str | None = None,
    follow_up_questions: list[str] | None = None,
    include_related_projects: bool = True,
    include_follow_up: bool = True,
) -> str:
    clean_highlights = [(label.strip(), _clean_text(value)) for label, value in highlights if label.strip() and _clean_text(value)]
    clean_highlights = clean_highlights[:6]
    lines = [title, "", "KEY HIGHLIGHTS"]
    if clean_highlights:
        lines.extend([f"• **{label}:** {value}" for label, value in clean_highlights])
    else:
        lines.append("• **Note:** Some details aren't available in the portfolio text for this item.")

    if include_related_projects:
        normalized_related = _normalize_sources(_filter_project_sources(related_projects or []))[:3]
        if normalized_related:
            lines.extend(["", "RELATED PROJECTS"])
            for src in normalized_related:
                url = str(src.get("url") or "").strip()
                if not url:
                    continue
                related_title = _clean_text(str(src.get("title") or "")) or "OBE Project"
                lines.append(f"- [{related_title}]({url})")

    if include_follow_up:
        questions = [q for q in (follow_up_questions or []) if q]
        if not questions and follow_up:
            questions = [follow_up]
        if questions:
            lines.append("")
            lines.append(f"Follow-up question: {questions[0]}")
    return "\n".join(lines).strip()


def _build_structured_fallback(title: str, *, include_follow_up: bool = True) -> str:
    return _format_structured_answer(
        title=title or "OBE Portfolio Highlights",
        highlights=[
            ("Summary", "I couldn't retrieve enough portfolio text to answer that precisely."),
            ("Try", "Ask about a specific project name, or choose a category (Villas / Commercial / Sports / Education)."),
            ("Next step", "Tell me your city (e.g., Dubai) or the project type."),
        ],
        related_projects=[],
        follow_up=FALLBACK_FOLLOW_UP,
        include_related_projects=False,
        include_follow_up=include_follow_up,
    )


def _build_category_fallback_answer(category_slug: str, *, include_follow_up: bool = True) -> str:
    return _build_structured_fallback(_category_title(category_slug), include_follow_up=include_follow_up)


def _format_related_projects(sources: list[dict[str, str | None]]) -> list[str]:
    projects: list[str] = []
    for src in sources[:3]:
        title = str(src.get("title") or "OBE Project").strip()
        url = str(src.get("url") or "").strip()
        if not url:
            continue
        projects.append(f"- [{title}]({url})")
    return projects


def _drop_unsupported_highlights(
    highlights: list[tuple[str, str]],
    context_text: str,
    strict_text: bool = False,
) -> list[tuple[str, str]]:
    context_norm = _normalize_for_match(context_text)
    if not context_norm:
        return []
    supported: list[tuple[str, str]] = []
    for label, value in highlights:
        value_norm = _normalize_for_match(value)
        if not value_norm:
            continue
        label_norm = _normalize_for_match(label)
        must_ground = bool(re.search(r"\d", value)) or any(
            marker in label_norm for marker in ("location", "area", "floors")
        )
        if not must_ground and not strict_text:
            supported.append((label, value))
            continue

        if re.search(r"\d", value):
            nums = re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", value)
            context_digits = re.sub(r"[^0-9.]+", "", context_norm)
            nums_ok = all(num.replace(",", "") in context_digits for num in nums)
            if not nums_ok:
                continue
        tokens = [tok for tok in value_norm.split() if len(tok) >= 4]
        token_hits = sum(1 for tok in tokens if tok in context_norm)
        if tokens and token_hits < 1:
            continue
        if strict_text and tokens and token_hits < 2:
            continue
        supported.append((label, value))
    return supported


def _ensure_category_core_highlights(
    highlights: list[tuple[str, str]],
    matches: list[dict[str, Any]],
    sources: list[dict[str, str | None]],
) -> list[tuple[str, str]]:
    existing = {label.strip().lower() for label, _ in highlights}
    required = _extract_category_highlights(matches=matches, sources=sources, min_occurrences=1)
    merged = list(highlights)
    for label, value in required:
        key = label.strip().lower()
        if key in existing:
            continue
        if key in {"built-up areas", "location", "locations", "number of floors"}:
            merged.append((label, value))
            existing.add(key)
    return merged[:6]


def _extract_llm_highlights(answer: str) -> list[tuple[str, str]]:
    highlights: list[tuple[str, str]] = []
    for raw in (answer or "").splitlines():
        line = raw.strip()
        if not line.startswith("- ") and not line.startswith("* ") and not line.startswith("â€¢ ") and not line.startswith("• "):
            continue
        line = re.sub(r"^\s*(?:[-*]|â€¢|•)\s*", "", line).strip()
        m = re.match(r"^\*\*([^*]+):\*\*\s*(.+)$", line)
        if m:
            highlights.append((_clean_text(m.group(1)), _clean_text(m.group(2))))
            continue
        if ":" in line:
            label, value = line.split(":", 1)
            highlights.append((_clean_text(label), _clean_text(value)))
    return highlights[:6]


def _format_answer_markdown(
    answer: str,
    context_text: str,
    sources: list[dict[str, str | None]],
    route_kind: str,
    category_title: str | None = None,
    matches: list[dict[str, Any]] | None = None,
    include_follow_up: bool = True,
) -> str:
    title = "OBE Portfolio Highlights"
    if route_kind == ROUTE_CATEGORY_OVERVIEW and category_title:
        title = category_title
    elif route_kind == ROUTE_PROJECT_DETAIL and sources:
        title = str(sources[0].get("title") or "Project Overview").strip() or "Project Overview"

    follow_up_questions = _extract_follow_up_questions(answer)
    highlights = _extract_llm_highlights(answer)
    if not highlights:
        highlights = _extract_category_highlights(matches=[], sources=sources)
    highlights = _drop_unsupported_highlights(
        highlights,
        context_text=context_text,
        strict_text=False,
    )
    if route_kind == ROUTE_CATEGORY_OVERVIEW:
        highlights = _ensure_category_core_highlights(highlights, matches or [], sources)
        if not highlights:
            snippet_pairs = _extract_overview_snippets(matches or [], limit=3)
            if snippet_pairs:
                highlights = [(title, text) for title, text in snippet_pairs]
    if not highlights:
        highlights = [("Note", "Some details aren't available in the portfolio text for this item.")]
    return _format_structured_answer(
        title=title,
        highlights=highlights,
        related_projects=sources if route_kind == ROUTE_PROJECT_DETAIL else [],
        follow_up_questions=_validate_or_replace_follow_ups(follow_up_questions, context_text, sources),
        include_follow_up=include_follow_up,
    )


def _sanitize_answer(
    answer: str,
    context_text: str = "",
    sources: list[dict[str, str | None]] | None = None,
    route_kind: str = ROUTE_GENERAL_RAG,
    category_title: str | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> str:
    cleaned = _strip_follow_up_section(answer or "")
    if not cleaned:
        return _build_structured_fallback("OBE Portfolio Highlights")

    lowered = cleaned.lower()
    if any(marker in lowered for marker in _INSTRUCTION_LEAK_MARKERS):
        return _build_structured_fallback("OBE Portfolio Highlights")
    if "i don't know based on the available sources" in lowered:
        return _build_structured_fallback("OBE Portfolio Highlights")
    return _format_answer_markdown(
        cleaned,
        context_text=context_text,
        sources=sources or [],
        route_kind=route_kind,
        category_title=category_title,
        matches=matches,
        include_follow_up=route_kind not in {ROUTE_CATEGORY_OVERVIEW, ROUTE_CATEGORY_DEEP_DIVE},
    )


def _retrieve_with_context(
    question: str,
    top_k: int,
    context_urls: list[str] | None,
    category_slug: str | None = None,
) -> list[dict[str, Any]]:
    project_id = _extract_explicit_project_id(question)
    project_filters: list[str] = []
    if project_id:
        project_filters.append(f"https://obearchitects.com/obe/project-detail.php?id={project_id}")
    for url in context_urls or []:
        if _PROJECT_DETAIL_RE.search(url):
            project_filters.append(url)
    if project_filters:
        project_matches = _stable_sort_matches(
            retrieve_chunks(
                query=question,
                top_k=top_k,
                min_score=0.0,
                url_filters=project_filters,
            )
        )
        if project_matches:
            return project_matches[:top_k]

    if not context_urls:
        base = retrieve_chunks(query=question, top_k=top_k, min_score=0.0)
        prioritized = _prioritize_category_matches(base, category_slug or "", top_k)
        if category_slug:
            return _filter_to_category_slug(prioritized, category_slug, top_k)
        return prioritized

    preferred = _stable_sort_matches(retrieve_chunks(
        query=question,
        top_k=top_k,
        min_score=0.0,
        url_filters=context_urls,
    ))

    preferred_enough = len(preferred) >= max(2, min(4, top_k))
    if preferred_enough:
        prioritized = _prioritize_category_matches(preferred, category_slug or "", top_k)
        if category_slug:
            return _filter_to_category_slug(prioritized, category_slug, top_k)
        return prioritized

    fallback = _stable_sort_matches(retrieve_chunks(query=question, top_k=top_k, min_score=0.0))
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in preferred + fallback:
        key = (str(item.get("url") or ""), str(item.get("chunk_text") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= top_k:
            break
    prioritized = _prioritize_category_matches(merged, category_slug or "", top_k)
    if category_slug:
        return _filter_to_category_slug(prioritized, category_slug, top_k)
    return prioritized


def _filter_to_category_slug(matches: list[dict[str, Any]], category_slug: str, top_k: int) -> list[dict[str, Any]]:
    aliases = _category_url_aliases(category_slug)
    strict: list[dict[str, Any]] = []
    loose: list[dict[str, Any]] = []
    for item in _stable_sort_matches(matches):
        url = str(item.get("url") or "").lower()
        title = str(item.get("title") or "").lower()
        chunk_text = str(item.get("chunk_text") or "").lower()
        if any(f"category={alias}" in url for alias in aliases):
            strict.append(item)
            continue
        blob = " ".join([url, title, chunk_text])
        if any(alias in blob for alias in aliases) or _match_is_category_relevant(item, category_slug):
            loose.append(item)
    picked = strict or loose
    return picked[:top_k] if picked else _stable_sort_matches(matches)[:top_k]


def answer_question(
    question: str,
    top_k: int | None = None,
    context_urls: list[str] | None = None,
    follow_up_seed: str | None = None,
    use_context_urls: bool = False,
    follow_up_count: int | None = None,
    last_category_slug: str | None = None,
    category_followup_step: int | None = None,
) -> RagAnswerResult:
    deep_dive_topic = detect_category_deep_dive(question)
    category_slug = _detect_category_slug(question)
    if deep_dive_topic:
        inferred = category_slug or last_category_slug or _infer_category_from_context_urls(context_urls)
        if inferred:
            route_kind = ROUTE_CATEGORY_DEEP_DIVE
            category_slug = inferred
        else:
            route_kind, category_slug = _resolve_route(question, context_urls)
            deep_dive_topic = None
    else:
        route_kind, category_slug = _resolve_route(question, context_urls)
    is_category_route = route_kind in {ROUTE_CATEGORY_OVERVIEW, ROUTE_CATEGORY_DEEP_DIVE}
    if is_category_route and not use_context_urls:
        effective_context_urls = None
    else:
        effective_context_urls = context_urls or None
    if route_kind == ROUTE_CATEGORY_OVERVIEW:
        use_top_k = 10
        min_similarity = _clamp(settings.min_similarity_score_category)
    elif route_kind == ROUTE_CATEGORY_DEEP_DIVE:
        use_top_k = 12
        min_similarity = _clamp(settings.min_similarity_score_category)
    elif route_kind == ROUTE_PROJECT_DETAIL:
        use_top_k = 6
        min_similarity = _clamp(settings.min_similarity_score_project)
    else:
        use_top_k = 8
        min_similarity = _clamp(settings.min_similarity_score_project)
    context_limit = settings.rag_public_max_context_chars or settings.rag_max_context_chars
    min_confidence = 0.0 if is_category_route else _clamp(settings.rag_public_min_confidence)
    if category_followup_step is None:
        category_followup_step = 0
    if route_kind == ROUTE_CATEGORY_OVERVIEW:
        category_followup_step = 0

    def _category_follow_up_buttons(category_slug_value: str | None, route_value: str) -> list[str]:
        if not category_slug_value:
            return []
        if category_followup_step is not None and category_followup_step >= 3:
            return []
        options = _CATEGORY_FOLLOW_UPS_TEXT.get(category_slug_value, [])
        if not options:
            return []
        if route_value == ROUTE_CATEGORY_DEEP_DIVE:
            index = min(category_followup_step + 1, len(options) - 1)
        else:
            index = 0
        return [options[index]]

    suppress_follow_up = follow_up_count is not None and follow_up_count >= 3
    matches: list[dict[str, Any]] = []
    phrase = _extract_project_phrase(question) if route_kind == ROUTE_PROJECT_DETAIL else None
    if phrase and not context_urls:
        keyword_matches = _retrieve_keyword_matches(phrase, use_top_k)
        if keyword_matches:
            matches = keyword_matches
        else:
            matches = []
    try:
        if not phrase or not matches:
            matches = _retrieve_with_context(
                question=question,
                top_k=use_top_k,
                context_urls=effective_context_urls,
                category_slug=category_slug,
            )
    except Exception:
        logger.exception("Public RAG retrieval failed")
        fallback_answer = _build_category_fallback_answer(category_slug) if category_slug else _build_structured_fallback(
            "OBE Portfolio Highlights"
        )
        return RagAnswerResult(
            answer=fallback_answer,
            sources=[],
            confidence=0.0,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=None,
            retrieval_k=use_top_k,
            fallback_reason="other",
        )

    if route_kind == ROUTE_PROJECT_DETAIL:
        phrase = _extract_project_phrase(question)
        if phrase:
            phrase_lower = phrase.lower()
            filtered = [
                item for item in matches
                if phrase_lower in str(item.get("chunk_text") or "").lower()
                or phrase_lower in str(item.get("title") or "").lower()
            ]
            if filtered:
                matches = filtered[:use_top_k]

    confidence = _normalize_confidence(matches)
    top_score = float(matches[0].get("score") or 0.0) if matches else None
    if not matches:
        if category_slug and is_category_route:
            fallback_answer = _format_category_deep_dive_answer(
                deep_dive_topic or "features",
                category_slug,
                matches=[],
                sources=[],
                context_text="",
                related_projects=[],
            ) if route_kind == ROUTE_CATEGORY_DEEP_DIVE else _format_category_overview_answer(
                category_slug=category_slug,
                matches=[],
                sources=[],
                related_projects=[],
            )
        elif category_slug:
            fallback_answer = _build_category_fallback_answer(category_slug, include_follow_up=not suppress_follow_up)
        else:
            fallback_answer = _build_structured_fallback("OBE Portfolio Highlights", include_follow_up=not suppress_follow_up)
        return RagAnswerResult(
            answer=fallback_answer,
            sources=[],
            confidence=0.0,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=None,
            retrieval_k=use_top_k,
            fallback_reason="no_chunks",
        )
    if (not is_category_route) and (top_score is None or top_score < min_similarity):
        if category_slug:
            fallback_answer = _build_category_fallback_answer(category_slug, include_follow_up=not suppress_follow_up)
        else:
            fallback_answer = _build_structured_fallback("OBE Portfolio Highlights", include_follow_up=not suppress_follow_up)
        return RagAnswerResult(
            answer=fallback_answer,
            sources=[],
            confidence=confidence,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason="low_similarity",
        )
    if (not is_category_route) and confidence < min_confidence:
        if category_slug:
            fallback_answer = _build_category_fallback_answer(category_slug, include_follow_up=not suppress_follow_up)
        else:
            fallback_answer = _build_structured_fallback("OBE Portfolio Highlights", include_follow_up=not suppress_follow_up)
        return RagAnswerResult(
            answer=fallback_answer,
            sources=[],
            confidence=confidence,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason="low_similarity",
        )

    context, sources = _build_context(matches=matches, max_chars=context_limit)
    if not context or not sources:
        if category_slug and is_category_route:
            fallback_answer = _format_category_deep_dive_answer(
                deep_dive_topic or "features",
                category_slug,
                matches=[],
                sources=[],
                context_text="",
                related_projects=[],
            ) if route_kind == ROUTE_CATEGORY_DEEP_DIVE else _format_category_overview_answer(
                category_slug=category_slug,
                matches=[],
                sources=[],
                related_projects=[],
            )
        elif category_slug:
            fallback_answer = _build_category_fallback_answer(category_slug, include_follow_up=not suppress_follow_up)
        else:
            fallback_answer = _build_structured_fallback("OBE Portfolio Highlights", include_follow_up=not suppress_follow_up)
        return RagAnswerResult(
            answer=fallback_answer,
            sources=[],
            confidence=confidence,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason="other",
        )

    category_overview_sources = _strip_internal_source_fields(
        _normalize_sources(sources)
    )
    final_sources = _strip_internal_source_fields(
        _normalize_sources(_filter_project_sources(sources))[:3]
    )
    public_sources = final_sources
    if is_category_route and context_urls and not use_context_urls:
        public_sources = []

    if route_kind == ROUTE_CATEGORY_DEEP_DIVE and category_slug:
        deep_dive_answer = _format_category_deep_dive_answer(
            deep_dive_topic or "features",
            category_slug,
            matches=matches,
            sources=category_overview_sources,
            context_text=context,
            related_projects=[],
        )
        return RagAnswerResult(
            answer=deep_dive_answer,
            sources=public_sources,
            confidence=confidence,
            follow_up_buttons=_category_follow_up_buttons(category_slug, route_kind),
            route_taken="rag",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason=None,
        )

    if category_slug:
        user_prompt = f"Question: {question}\n\nSOURCES:\n{context}"
        try:
            client = OllamaClient(timeout_seconds=30.0)
            llm_options = {
                "temperature": _clamp(settings.rag_llm_temperature),
                "top_p": _clamp(settings.rag_llm_top_p),
                "repeat_penalty": max(1.0, float(settings.rag_llm_repeat_penalty)),
            }
            answer = client.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                options=llm_options,
            )
            safe_answer = _sanitize_answer(
                answer,
                context_text=context,
                sources=final_sources,
                route_kind=route_kind,
                category_title=_category_title(category_slug),
                matches=matches,
            )
            if route_kind == ROUTE_CATEGORY_OVERVIEW:
                safe_answer = _strip_follow_up_section(safe_answer)
            elif follow_up_count is not None and follow_up_count >= 3:
                safe_answer = _strip_follow_up_section(safe_answer)
            return RagAnswerResult(
                answer=safe_answer,
                sources=public_sources,
                confidence=confidence,
                follow_up_buttons=_category_follow_up_buttons(category_slug, route_kind),
                route_taken="rag",
                route_kind=route_kind,
                category_slug=category_slug,
                retrieval_top_score=top_score,
                retrieval_k=use_top_k,
                fallback_reason=None,
            )
        except Exception:
            logger.exception("Public RAG generation failed")
            extracted = _format_category_overview_answer(
                category_slug=category_slug,
                matches=matches,
                sources=category_overview_sources,
                related_projects=final_sources,
                follow_up_questions=_validate_or_replace_follow_ups(
                    _safe_follow_up_candidates(final_sources),
                    context,
                    final_sources,
                ),
            )
            extracted = _strip_follow_up_section(extracted)
            return RagAnswerResult(
                answer=extracted,
                sources=public_sources,
                confidence=confidence,
                follow_up_buttons=_category_follow_up_buttons(category_slug, route_kind),
                route_taken="rag",
                route_kind=route_kind,
                category_slug=category_slug,
                retrieval_top_score=top_score,
                retrieval_k=use_top_k,
                fallback_reason=None,
            )

    user_prompt = f"Question: {question}\n\nSOURCES:\n{context}"

    try:
        client = OllamaClient(timeout_seconds=30.0)
        llm_options = {
            "temperature": _clamp(settings.rag_llm_temperature),
            "top_p": _clamp(settings.rag_llm_top_p),
            "repeat_penalty": max(1.0, float(settings.rag_llm_repeat_penalty)),
        }
        answer = client.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options=llm_options,
        )
        safe_answer = _sanitize_answer(
            answer,
            context_text=context,
            sources=final_sources,
            route_kind=route_kind,
        )
        return RagAnswerResult(
            answer=safe_answer,
            sources=public_sources,
            confidence=confidence,
            follow_up_buttons=[],
            route_taken="rag",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason=None,
        )
    except Exception:
        logger.exception("Public RAG generation failed")
        fallback_answer = _build_category_fallback_answer(category_slug) if category_slug else _build_structured_fallback(
            "OBE Portfolio Highlights"
        )
        return RagAnswerResult(
            answer=fallback_answer,
            sources=_strip_internal_source_fields(_normalize_sources(_filter_project_sources(sources))[:3]),
            confidence=confidence,
            follow_up_buttons=[],
            route_taken="fallback",
            route_kind=route_kind,
            category_slug=category_slug,
            retrieval_top_score=top_score,
            retrieval_k=use_top_k,
            fallback_reason="other",
        )







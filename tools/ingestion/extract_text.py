from __future__ import annotations

import re

from bs4 import BeautifulSoup


WHITESPACE_RE = re.compile(r"[ \t]+")
NEWLINES_RE = re.compile(r"\n{3,}")


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def extract_title(html: str) -> str:
    soup = _make_soup(html)
    if soup.title and soup.title.text:
        title = soup.title.text.strip()
        if title:
            return title
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return ""


def fallback_extract_text(html: str) -> str:
    soup = _make_soup(html)
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_main_text(html: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            output_format="txt",
            include_comments=False,
            include_links=False,
        )
        if extracted and extracted.strip():
            return extracted.strip()
    except Exception:
        pass
    return fallback_extract_text(html).strip()


def normalize_whitespace(text: str) -> str:
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return NEWLINES_RE.sub("\n\n", normalized).strip()

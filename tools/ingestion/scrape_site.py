from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.settings import settings
from tools.ingestion.extract_text import extract_main_text, extract_title
from tools.ingestion.robots import RobotsPolicy, parse_robots_txt
from tools.ingestion.utils import (
    compute_sha256,
    is_in_path_scope,
    is_probable_asset,
    is_same_registrable_domain,
    normalize_url,
    top_paths,
    write_jsonl,
)


CATEGORY_RE = re.compile(r"projectlists\.php\?category=[A-Za-z0-9_%\-]+")
DETAIL_RE = re.compile(r"project-detail\.php\?id=\d+")
CATEGORY_SLUG_RE = re.compile(r"projectlists\.php\?category=([A-Za-z0-9_%\-]+)")
DETAIL_ID_RE = re.compile(r"project-detail\.php\?id=(\d+)")
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
ASSET_PATH_SEGMENTS = {"/css/", "/js/", "/images/", "/img/", "/assets/"}

HUB_PAGES = [
    "https://obearchitects.com/obe/projects.php",
    "https://obearchitects.com/obe/index.php",
]

CORE_PAGES = [
    "https://obearchitects.com/obe/index.php",
    "https://obearchitects.com/obe/projects.php",
    "https://obearchitects.com/obe/projectlists.php",
    "https://obearchitects.com/obe/expertise.php",
    "https://obearchitects.com/obe/media.php",
    "https://obearchitects.com/obe/about-us.php",
    "https://obearchitects.com/obe/contact-us.php",
]


@dataclass
class ScrapeReport:
    discovered_urls_count: int = 0
    fetched_urls_count: int = 0
    kept_docs_count: int = 0
    skipped_small_count: int = 0
    skipped_robots_count: int = 0
    skipped_invalid_scope_count: int = 0
    skipped_query_filtered_count: int = 0
    category_pages_count: int = 0
    project_detail_pages_count: int = 0
    discovered_categories_count: int = 0
    discovered_project_ids_count: int = 0
    project_detail_pages_fetched_count: int = 0
    category_pages_fetched_count: int = 0
    errors_by_type: dict[str, int] | None = None
    top_10_paths_crawled: list[dict] | None = None

    def to_dict(self) -> dict:
        return {
            "discovered_urls_count": self.discovered_urls_count,
            "fetched_urls_count": self.fetched_urls_count,
            "kept_docs_count": self.kept_docs_count,
            "skipped_small_count": self.skipped_small_count,
            "skipped_robots_count": self.skipped_robots_count,
            "skipped_invalid_scope_count": self.skipped_invalid_scope_count,
            "skipped_query_filtered_count": self.skipped_query_filtered_count,
            "errors_by_type": self.errors_by_type or {},
            "category_pages_count": self.category_pages_count,
            "project_detail_pages_count": self.project_detail_pages_count,
            "discovered_categories_count": self.discovered_categories_count,
            "discovered_project_ids_count": self.discovered_project_ids_count,
            "project_detail_pages_fetched_count": self.project_detail_pages_fetched_count,
            "category_pages_fetched_count": self.category_pages_fetched_count,
            "top_10_paths_crawled": self.top_10_paths_crawled or [],
        }


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_robots_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
def _fetch_text(client: httpx.Client, url: str) -> str:
    response = client.get(url)
    response.raise_for_status()
    return response.text


def _get_robots_policy(client: httpx.Client, base_url: str, user_agent: str, respect_robots: bool) -> RobotsPolicy:
    robots_url = _build_robots_url(base_url)
    try:
        content = _fetch_text(client, robots_url)
        return parse_robots_txt(content, user_agent=user_agent)
    except Exception as exc:  # pragma: no cover - network failures depend on environment
        if respect_robots:
            raise RuntimeError(
                f"Failed to fetch robots.txt at {robots_url} while SCRAPE_RESPECT_ROBOTS=true"
            ) from exc
        return RobotsPolicy([])


def _discover_sitemaps(client: httpx.Client, base_url: str, policy: RobotsPolicy) -> list[str]:
    urls = set(policy.sitemaps)
    parsed = urlparse(base_url)
    urls.add(f"{parsed.scheme}://{parsed.netloc}/sitemap.xml")
    discovered: set[str] = set()
    queue = deque(urls)
    while queue:
        sitemap_url = queue.popleft()
        try:
            xml_text = _fetch_text(client, sitemap_url)
            root = ET.fromstring(xml_text)
        except Exception:
            continue
        for loc in root.findall(".//{*}loc"):
            if not loc.text:
                continue
            value = loc.text.strip()
            if not value:
                continue
            if value.endswith(".xml"):
                queue.append(value)
            else:
                discovered.add(value)
    return sorted(discovered)


def extract_category_slugs(html: str) -> set[str]:
    return {slug for slug in CATEGORY_SLUG_RE.findall(html)}


def extract_project_ids(html: str) -> set[str]:
    return {project_id for project_id in DETAIL_ID_RE.findall(html)}


def _build_category_url(base_url: str, slug: str) -> str:
    encoded = quote(slug, safe="%-_")
    return urljoin(base_url, f"projectlists.php?category={encoded}")


def _build_project_detail_url(base_url: str, project_id: str) -> str:
    return urljoin(base_url, f"project-detail.php?id={project_id}")


def _discover_links_from_html(current_url: str, html: str, base_url: str) -> list[str]:
    links: list[str] = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        links.append(urljoin(current_url, a.get("href", "")))

    for match in HREF_RE.findall(html):
        links.append(urljoin(current_url, match))
    for match in CATEGORY_RE.findall(html):
        links.append(urljoin(base_url, match))
    for match in DETAIL_RE.findall(html):
        links.append(urljoin(base_url, match))
    return links


def _is_asset_like_dynamic_path(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if not path.endswith(".php"):
        return False
    return any(segment in path for segment in ASSET_PATH_SEGMENTS)


def _normalize_in_scope(
    url: str,
    base_url: str,
    path_prefix: str,
    allowed_query_keys: list[str],
    allow_subdomains: bool,
) -> tuple[str | None, str]:
    normalized, removed_unknown = normalize_url(
        url=url,
        base_url=base_url,
        allowed_query_keys=allowed_query_keys,
    )
    if not normalized:
        return None, "invalid"
    reason = "query_filtered" if removed_unknown else "ok"
    if not is_same_registrable_domain(normalized, base_url, allow_subdomains=allow_subdomains):
        return None, "scope"
    if not is_in_path_scope(normalized, path_prefix=path_prefix):
        return None, "scope"
    if _is_asset_like_dynamic_path(normalized):
        return None, "scope"
    if is_probable_asset(normalized):
        return None, "asset"
    return normalized, reason


def _can_fetch_url(url: str, policy: RobotsPolicy, report: ScrapeReport) -> bool:
    if settings.scrape_respect_robots and not policy.can_fetch(url):
        report.skipped_robots_count += 1
        return False
    return True


def _rate_limit(last_fetch_at: list[float], rps: float) -> None:
    elapsed = time.monotonic() - last_fetch_at[0]
    target_gap = 1.0 / max(rps, 0.1)
    if elapsed < target_gap:
        time.sleep(target_gap - elapsed)
    last_fetch_at[0] = time.monotonic()


def _fetch_html_page(
    client: httpx.Client,
    url: str,
    report: ScrapeReport,
    last_fetch_at: list[float],
    rps: float,
) -> str | None:
    _rate_limit(last_fetch_at, rps)
    try:
        response = client.get(url)
        report.fetched_urls_count += 1
    except Exception as exc:  # pragma: no cover - network dependent
        name = type(exc).__name__
        report.errors_by_type[name] = report.errors_by_type.get(name, 0) + 1
        return None

    if response.status_code >= 400:
        key = f"http_{response.status_code}"
        report.errors_by_type[key] = report.errors_by_type.get(key, 0) + 1
        return None

    content_type = (response.headers.get("content-type") or "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return None
    return response.text


def _upsert_document(
    docs: list[dict],
    seen_hashes: set[str],
    report: ScrapeReport,
    url: str,
    html: str,
    min_text_len: int,
) -> None:
    title = extract_title(html)
    text = extract_main_text(html)
    if len(text) < min_text_len:
        report.skipped_small_count += 1
        return
    content_hash = compute_sha256(text)
    if content_hash in seen_hashes:
        return
    seen_hashes.add(content_hash)
    docs.append(
        {
            "url": url,
            "title": title,
            "text": text,
            "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
            "content_hash": content_hash,
            "source": "obearchitects_site",
        }
    )
    report.kept_docs_count += 1


def _run_structured_discovery(
    client: httpx.Client,
    report: ScrapeReport,
    docs: list[dict],
    seen_hashes: set[str],
    fetched_paths: list[str],
    max_pages_value: int,
    rps_value: float,
    min_text_len: int,
    robots_policy: RobotsPolicy,
) -> tuple[bool, set[str], set[str]]:
    last_fetch_at = [0.0]
    fetched_count = 0
    categories: set[str] = set()
    project_ids: set[str] = set()

    # Step A: discover categories from hubs.
    for hub in HUB_PAGES:
        normalized, reason = _normalize_in_scope(
            url=hub,
            base_url=settings.scrape_base_url,
            path_prefix=settings.scrape_path_prefix,
            allowed_query_keys=settings.scrape_allowed_query_keys,
            allow_subdomains=settings.scrape_allow_subdomains,
        )
        if reason == "query_filtered":
            report.skipped_query_filtered_count += 1
        if not normalized:
            report.skipped_invalid_scope_count += 1
            continue
        if not _can_fetch_url(normalized, robots_policy, report):
            continue
        if fetched_count >= max_pages_value:
            break
        html = _fetch_html_page(client, normalized, report, last_fetch_at, rps_value)
        fetched_count += 1
        if not html:
            continue
        fetched_paths.append(normalized)
        categories.update(extract_category_slugs(html))

    category_urls: list[str] = []
    for slug in sorted(categories):
        category_url = _build_category_url(settings.scrape_base_url, slug)
        normalized, reason = _normalize_in_scope(
            url=category_url,
            base_url=settings.scrape_base_url,
            path_prefix=settings.scrape_path_prefix,
            allowed_query_keys=settings.scrape_allowed_query_keys,
            allow_subdomains=settings.scrape_allow_subdomains,
        )
        if reason == "query_filtered":
            report.skipped_query_filtered_count += 1
        if not normalized:
            report.skipped_invalid_scope_count += 1
            continue
        category_urls.append(normalized)

    # Step B: discover project ids from category pages.
    for category_url in category_urls:
        if fetched_count >= max_pages_value:
            break
        if not _can_fetch_url(category_url, robots_policy, report):
            continue
        html = _fetch_html_page(client, category_url, report, last_fetch_at, rps_value)
        fetched_count += 1
        if not html:
            continue
        fetched_paths.append(category_url)
        report.category_pages_fetched_count += 1
        report.category_pages_count += 1
        project_ids.update(extract_project_ids(html))

    report.discovered_categories_count = len(category_urls)
    report.discovered_project_ids_count = len(project_ids)
    report.discovered_urls_count = len(set(HUB_PAGES) | set(category_urls))

    if not category_urls or not project_ids:
        return False, set(category_urls), set(project_ids)

    # Step C: scrape all project detail pages.
    for project_id in sorted(project_ids, key=int):
        if fetched_count >= max_pages_value:
            break
        detail_url = _build_project_detail_url(settings.scrape_base_url, project_id)
        normalized, reason = _normalize_in_scope(
            url=detail_url,
            base_url=settings.scrape_base_url,
            path_prefix=settings.scrape_path_prefix,
            allowed_query_keys=settings.scrape_allowed_query_keys,
            allow_subdomains=settings.scrape_allow_subdomains,
        )
        if reason == "query_filtered":
            report.skipped_query_filtered_count += 1
        if not normalized:
            report.skipped_invalid_scope_count += 1
            continue
        if not _can_fetch_url(normalized, robots_policy, report):
            continue
        html = _fetch_html_page(client, normalized, report, last_fetch_at, rps_value)
        fetched_count += 1
        if not html:
            continue
        fetched_paths.append(normalized)
        report.project_detail_pages_fetched_count += 1
        report.project_detail_pages_count += 1
        _upsert_document(docs, seen_hashes, report, normalized, html, min_text_len)

    # Core non-project pages.
    for page in CORE_PAGES:
        if fetched_count >= max_pages_value:
            break
        normalized, reason = _normalize_in_scope(
            url=page,
            base_url=settings.scrape_base_url,
            path_prefix=settings.scrape_path_prefix,
            allowed_query_keys=settings.scrape_allowed_query_keys,
            allow_subdomains=settings.scrape_allow_subdomains,
        )
        if reason == "query_filtered":
            report.skipped_query_filtered_count += 1
        if not normalized:
            report.skipped_invalid_scope_count += 1
            continue
        if not _can_fetch_url(normalized, robots_policy, report):
            continue
        html = _fetch_html_page(client, normalized, report, last_fetch_at, rps_value)
        fetched_count += 1
        if not html:
            continue
        fetched_paths.append(normalized)
        _upsert_document(docs, seen_hashes, report, normalized, html, min_text_len)

    report.discovered_urls_count = len(set(HUB_PAGES) | set(category_urls) | {p for p in CORE_PAGES})
    return True, set(category_urls), set(project_ids)


def _run_bfs_fallback(
    client: httpx.Client,
    report: ScrapeReport,
    docs: list[dict],
    seen_hashes: set[str],
    fetched_paths: list[str],
    max_pages_value: int,
    rps_value: float,
    min_text_len: int,
    robots_policy: RobotsPolicy,
) -> None:
    sitemap_urls = _discover_sitemaps(client, settings.scrape_base_url, robots_policy)
    seeds = [
        settings.scrape_start_url,
        *CORE_PAGES,
    ]
    initial_urls = sitemap_urls if sitemap_urls else seeds
    queue: deque[str] = deque()
    queued: set[str] = set()
    visited: set[str] = set()

    for seed in initial_urls:
        normalized, reason = _normalize_in_scope(
            url=seed,
            base_url=settings.scrape_base_url,
            path_prefix=settings.scrape_path_prefix,
            allowed_query_keys=settings.scrape_allowed_query_keys,
            allow_subdomains=settings.scrape_allow_subdomains,
        )
        if reason == "query_filtered":
            report.skipped_query_filtered_count += 1
        if not normalized:
            if reason == "scope":
                report.skipped_invalid_scope_count += 1
            continue
        if normalized not in queued:
            queue.append(normalized)
            queued.add(normalized)

    last_fetch_at = [0.0]
    while queue and len(visited) < max_pages_value:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        report.discovered_urls_count = max(report.discovered_urls_count, len(queued))
        if not _can_fetch_url(current, robots_policy, report):
            continue
        html = _fetch_html_page(client, current, report, last_fetch_at, rps_value)
        if not html:
            continue
        fetched_paths.append(current)
        if CATEGORY_RE.search(current):
            report.category_pages_count += 1
            report.category_pages_fetched_count += 1
        if DETAIL_RE.search(current):
            report.project_detail_pages_count += 1
            report.project_detail_pages_fetched_count += 1
        _upsert_document(docs, seen_hashes, report, current, html, min_text_len)

        for discovered in _discover_links_from_html(current, html, settings.scrape_base_url):
            normalized, reason = _normalize_in_scope(
                url=discovered,
                base_url=settings.scrape_base_url,
                path_prefix=settings.scrape_path_prefix,
                allowed_query_keys=settings.scrape_allowed_query_keys,
                allow_subdomains=settings.scrape_allow_subdomains,
            )
            if reason == "query_filtered":
                report.skipped_query_filtered_count += 1
            if not normalized:
                if reason == "scope":
                    report.skipped_invalid_scope_count += 1
                continue
            if normalized in queued or normalized in visited:
                continue
            queue.append(normalized)
            queued.add(normalized)


def _structured_mode_enabled(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host == "obearchitects.com" or host.endswith(".obearchitects.com")


def run_scrape(
    output_dir: str | None = None,
    max_pages: int | None = None,
    rps: float | None = None,
) -> dict:
    scrape_output_dir = Path(output_dir or settings.scrape_output_dir)
    max_pages_value = max_pages or settings.scrape_max_pages
    rps_value = rps or settings.scrape_rps
    min_text_len = 200

    report = ScrapeReport(errors_by_type={})
    fetched_paths: list[str] = []
    docs: list[dict] = []
    seen_hashes: set[str] = set()

    headers = {"User-Agent": settings.scrape_user_agent}
    with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
        robots_policy = _get_robots_policy(
            client=client,
            base_url=settings.scrape_base_url,
            user_agent=settings.scrape_user_agent,
            respect_robots=settings.scrape_respect_robots,
        )

        used_structured = False
        if _structured_mode_enabled(settings.scrape_base_url):
            used_structured, _, _ = _run_structured_discovery(
                client=client,
                report=report,
                docs=docs,
                seen_hashes=seen_hashes,
                fetched_paths=fetched_paths,
                max_pages_value=max_pages_value,
                rps_value=rps_value,
                min_text_len=min_text_len,
                robots_policy=robots_policy,
            )

        if not used_structured:
            _run_bfs_fallback(
                client=client,
                report=report,
                docs=docs,
                seen_hashes=seen_hashes,
                fetched_paths=fetched_paths,
                max_pages_value=max_pages_value,
                rps_value=rps_value,
                min_text_len=min_text_len,
                robots_policy=robots_policy,
            )

    report.top_10_paths_crawled = top_paths(fetched_paths, top_n=10)

    docs_path = scrape_output_dir / "cleaned" / "documents.jsonl"
    write_jsonl(docs_path, docs)

    reports_dir = scrape_output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"run_{_timestamp()}.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    result = {
        "documents_path": str(docs_path),
        "report_path": str(report_path),
        "stats": report.to_dict(),
    }
    return result

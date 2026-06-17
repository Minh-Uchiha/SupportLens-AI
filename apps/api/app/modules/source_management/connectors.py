from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# A loaded document as (external_id, title, text). Connectors normalize whatever the
# source system returns into this shared shape so ingestion stays connector-agnostic.
LoadedDocument = tuple[str, str, str]

_INLINE_DEFAULT = "SupportLens AI requires citations for every substantive support answer."


def _load_inline(name: str, connection_ref: str) -> list[LoadedDocument]:
    body = connection_ref.strip() or _INLINE_DEFAULT
    return [("inline-doc", name, body)]


def _load_filesystem(name: str, connection_ref: str) -> list[LoadedDocument]:
    path = Path(connection_ref)
    if not path.exists():
        raise FileNotFoundError(f"Source path does not exist: {path}")
    files = sorted([p for p in path.rglob("*.md") if p.is_file()]) if path.is_dir() else [path]
    documents = [(str(p), p.stem.replace("-", " ").title(), p.read_text(encoding="utf-8")) for p in files]
    logger.info("Filesystem connector loaded %d documents from %s", len(documents), connection_ref)
    return documents


def _strip_html(raw: str) -> str:
    """Reduce HTML to readable text so retrieval indexes content, not markup.

    Intentionally simple (regex-based) to avoid a new dependency; good enough for the
    documentation-style sources v1 targets.
    """
    import re

    without_scripts = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    collapsed = re.sub(r"\s+", " ", without_tags)
    return collapsed.strip()


# Many documentation sites and CDNs reject requests without a browser-like User-Agent
# (returning 403/405), so send one by default. Connectors can still be customized via
# register_connector if a source needs auth headers or a different client.
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 SupportLensBot/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _load_http(name: str, connection_ref: str) -> list[LoadedDocument]:
    if not connection_ref.strip():
        raise ValueError("HTTP source requires a URL in connection_ref")
    try:
        import httpx

        response = httpx.get(connection_ref, timeout=30.0, follow_redirects=True, headers=_HTTP_HEADERS)
        response.raise_for_status()
        body = response.text
    except Exception:
        # Log the fetch failure and re-raise so the sync job records a failed status while
        # preserving the last-known-good index.
        logger.error("HTTP connector failed to fetch %s", connection_ref, exc_info=True)
        raise
    content_type = ""
    try:
        content_type = response.headers.get("content-type", "")
    except Exception:
        content_type = ""
    text_body = _strip_html(body) if "html" in content_type.lower() or "<html" in body.lower() else body
    logger.info("HTTP connector loaded %s (%d chars)", connection_ref, len(text_body))
    return [(connection_ref, name, text_body)]


# Registry mapping a source type to its loader. New connectors register here without
# touching ingestion logic, which keeps the extension point obvious.
_CONNECTORS: dict[str, Callable[[str, str], list[LoadedDocument]]] = {
    "inline": _load_inline,
    "filesystem": _load_filesystem,
    "markdown": _load_filesystem,
    "http": _load_http,
    "url": _load_http,
}


def register_connector(source_type: str, loader: Callable[[str, str], list[LoadedDocument]]) -> None:
    _CONNECTORS[source_type] = loader


def load_documents_from_source(source_type: str, name: str, connection_ref: str) -> list[LoadedDocument]:
    loader = _CONNECTORS.get(source_type)
    if loader is None:
        raise ValueError(f"Unsupported source type: {source_type}")
    return loader(name, connection_ref)

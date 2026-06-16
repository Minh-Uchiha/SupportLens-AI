from __future__ import annotations

from app.modules.source_management.connectors import load_documents_from_source


def load_markdown_documents(root_path: str) -> list[dict[str, str]]:
    """Load markdown documents from a path using the shared filesystem connector."""
    documents = load_documents_from_source("filesystem", root_path, root_path)
    return [{"external_id": external_id, "title": title, "text": text} for external_id, title, text in documents]

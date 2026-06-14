from __future__ import annotations

from pathlib import Path


def load_markdown_documents(root_path: str) -> list[dict[str, str]]:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(root_path)
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    return [{"external_id": str(path), "title": path.stem, "text": path.read_text(encoding="utf-8")} for path in files]

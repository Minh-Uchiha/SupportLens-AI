from __future__ import annotations

def chunk_document(document_text: str, metadata: dict | None = None, target_tokens: int = 1000, overlap_tokens: int = 120) -> list[dict[str, object]]:
    words = document_text.split()
    if not words:
        return []
    step = max(target_tokens - overlap_tokens, 1)
    chunks = []
    for index, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start:start + target_tokens]
        if not chunk_words:
            continue
        chunks.append({"chunk_index": index, "text": " ".join(chunk_words), "metadata": metadata or {}})
        if start + target_tokens >= len(words):
            break
    return chunks

from __future__ import annotations

from collections import OrderedDict

from app.modules.retrieval.schemas import EvidenceChunk


def merge_and_rank(lexical_candidates: list[EvidenceChunk], vector_candidates: list[EvidenceChunk], limit: int = 8) -> list[EvidenceChunk]:
    merged: OrderedDict[str, EvidenceChunk] = OrderedDict()
    for candidate in lexical_candidates + vector_candidates:
        existing = merged.get(candidate.chunk_id)
        if existing is None or candidate.score > existing.score:
            merged[candidate.chunk_id] = candidate
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:limit]

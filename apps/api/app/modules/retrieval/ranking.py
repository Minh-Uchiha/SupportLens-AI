from __future__ import annotations

from collections import OrderedDict

from app.modules.retrieval.schemas import EvidenceChunk


def _normalize(candidates: list[EvidenceChunk]) -> dict[str, float]:
    """Scale a candidate list's raw scores into 0..1 so lexical and vector results compare.

    Lexical (ts_rank/overlap) and vector (cosine) scores live on different scales, so we
    min-max each list independently before merging to avoid one signal dominating purely
    because of its units.
    """
    if not candidates:
        return {}
    scores = [item.score for item in candidates]
    low, high = min(scores), max(scores)
    spread = high - low
    if spread <= 0:
        return {item.chunk_id: 1.0 for item in candidates}
    return {item.chunk_id: (item.score - low) / spread for item in candidates}


def merge_and_rank(
    lexical_candidates: list[EvidenceChunk],
    vector_candidates: list[EvidenceChunk],
    limit: int = 8,
) -> list[EvidenceChunk]:
    """Combine lexical and vector candidates into one ranked, de-duplicated evidence list."""
    lexical_norm = _normalize(lexical_candidates)
    vector_norm = _normalize(vector_candidates)

    merged: OrderedDict[str, EvidenceChunk] = OrderedDict()
    combined_scores: dict[str, float] = {}
    for candidate in lexical_candidates + vector_candidates:
        # A chunk found by both signals gets the sum of its normalized scores, so agreement
        # between lexical and vector retrieval ranks it above single-signal matches.
        normalized = lexical_norm.get(candidate.chunk_id, 0.0) + vector_norm.get(candidate.chunk_id, 0.0)
        if candidate.chunk_id not in merged:
            merged[candidate.chunk_id] = candidate
        combined_scores[candidate.chunk_id] = normalized

    ranked = []
    for chunk_id, chunk in merged.items():
        ranked.append(chunk.model_copy(update={"score": combined_scores[chunk_id]}))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]

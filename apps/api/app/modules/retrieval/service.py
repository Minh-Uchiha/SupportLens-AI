from __future__ import annotations

import math
import re
from collections import Counter

from app.modules.auth_policy.schemas import RequestContext
from app.modules.auth_policy.service import build_document_acl_filter
from app.modules.retrieval.ranking import merge_and_rank
from app.modules.retrieval.schemas import EvidenceChunk, EvidenceSet, RetrievalOptions
from app.modules.source_management.service import get_chunks_for_tenant, get_document

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _vector(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[key] * right.get(key, 0) for key in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _to_evidence(chunk, score: float) -> EvidenceChunk:
    document = get_document(chunk.document_id)
    return EvidenceChunk(
        chunk_id=chunk.id,
        source_id=chunk.source_id,
        document_id=chunk.document_id,
        text=chunk.text,
        citation_anchor=chunk.citation_anchor,
        freshness_status=document.freshness_status if document else "unknown",
        score=score,
    )


def lexical_search(context: RequestContext, query: str, options: RetrievalOptions) -> list[EvidenceChunk]:
    acl = build_document_acl_filter(context, options.source_ids)
    query_terms = set(tokenize(query))
    results: list[EvidenceChunk] = []
    for chunk in get_chunks_for_tenant(context):
        # Source filters are applied before scoring so unauthorized chunks never rank.
        if acl.allowed_source_ids and chunk.source_id not in acl.allowed_source_ids:
            continue
        terms = tokenize(chunk.text)
        if not terms:
            continue
        overlap = len(query_terms.intersection(terms))
        if overlap:
            results.append(_to_evidence(chunk, overlap / max(len(query_terms), 1)))
    return sorted(results, key=lambda item: item.score, reverse=True)[:50]


def vector_search(context: RequestContext, query: str, options: RetrievalOptions) -> list[EvidenceChunk]:
    acl = build_document_acl_filter(context, options.source_ids)
    query_vector = _vector(query)
    results: list[EvidenceChunk] = []
    for chunk in get_chunks_for_tenant(context):
        if acl.allowed_source_ids and chunk.source_id not in acl.allowed_source_ids:
            continue
        score = _cosine(query_vector, _vector(chunk.text))
        if score:
            results.append(_to_evidence(chunk, score))
    return sorted(results, key=lambda item: item.score, reverse=True)[:50]


def retrieve_evidence(context: RequestContext, query: str, options: RetrievalOptions | None = None) -> EvidenceSet:
    resolved_options = options or RetrievalOptions()
    lexical = lexical_search(context, query, resolved_options)
    vector = vector_search(context, query, resolved_options)
    ranked = merge_and_rank(lexical, vector, resolved_options.limit)
    # Low-confidence retrieval produces a refusal instead of unsupported generation.
    threshold_met = bool(ranked and ranked[0].score >= resolved_options.min_score)
    return EvidenceSet(query=query, chunks=ranked, threshold_met=threshold_met)

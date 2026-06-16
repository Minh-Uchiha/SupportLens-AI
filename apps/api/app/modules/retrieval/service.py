from __future__ import annotations

import logging
import math
import re

from sqlalchemy import bindparam, text

from app.db.session import current_session
from app.modules.auth_policy.schemas import RequestContext
from app.modules.auth_policy.service import build_document_acl_filter
from app.modules.llm_gateway.embeddings import embed_texts
from app.modules.retrieval.ranking import merge_and_rank
from app.modules.retrieval.schemas import EvidenceChunk, EvidenceSet, RetrievalOptions
from app.modules.source_management.service import get_chunks_for_tenant, get_document

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Candidate pool size per signal before merge/rerank (LLD: lexical top 50 + vector top 50).
_CANDIDATE_LIMIT = 50


def tokenize(text_value: str) -> list[str]:
    return _TOKEN_RE.findall(text_value.lower())


def _dialect() -> str:
    bind = current_session().get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


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


def _allowed_source_ids(context: RequestContext, options: RetrievalOptions) -> set[str] | None:
    acl = build_document_acl_filter(context, options.source_ids)
    return acl.allowed_source_ids or None


# --- Postgres path: native full-text + trigram + pgvector ----------------------------------


def _pg_lexical_search(context: RequestContext, query: str, allowed_sources: set[str] | None) -> list[EvidenceChunk]:
    # ts_rank scores full-text relevance; trigram similarity catches fuzzy/near-exact matches
    # (for example slightly misspelled error codes) that plain full-text would miss.
    sql = text(
        """
        SELECT id, source_id, document_id, text, citation_anchor,
               (ts_rank(tsv, plainto_tsquery('english', :query))
                + similarity(text, :query)) AS score
        FROM knowledge_chunks
        WHERE tenant_id = :tenant_id
          AND (tsv @@ plainto_tsquery('english', :query) OR text % :query)
          AND (:no_source_filter OR source_id IN :source_ids)
        ORDER BY score DESC
        LIMIT :limit
        """
    ).bindparams(bindparam("source_ids", expanding=True))
    return _run_chunk_query(context, sql, query, allowed_sources)


def _pg_vector_search(context: RequestContext, query_embedding: list[float], allowed_sources: set[str] | None) -> list[EvidenceChunk]:
    # 1 - cosine_distance gives a 0..1 similarity. NULL vectors (chunks never embedded) are
    # excluded so they do not rank ahead of real matches.
    vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
    sql = text(
        """
        SELECT id, source_id, document_id, text, citation_anchor,
               (1 - (embedding_vector <=> CAST(:query_vector AS vector))) AS score
        FROM knowledge_chunks
        WHERE tenant_id = :tenant_id
          AND embedding_vector IS NOT NULL
          AND (:no_source_filter OR source_id IN :source_ids)
        ORDER BY embedding_vector <=> CAST(:query_vector AS vector) ASC
        LIMIT :limit
        """
    ).bindparams(bindparam("source_ids", expanding=True))
    return _run_chunk_query(context, sql, None, allowed_sources, query_vector=vector_literal)


def _run_chunk_query(
    context: RequestContext,
    sql,
    query: str | None,
    allowed_sources: set[str] | None,
    query_vector: str | None = None,
) -> list[EvidenceChunk]:
    params: dict[str, object] = {
        "tenant_id": context.tenant_id,
        "limit": _CANDIDATE_LIMIT,
        # Expanding IN clauses cannot bind an empty list, so a sentinel flag disables the
        # source filter when the tenant has access to every source.
        "no_source_filter": allowed_sources is None,
        "source_ids": list(allowed_sources) if allowed_sources else [""],
    }
    if query is not None:
        params["query"] = query
    if query_vector is not None:
        params["query_vector"] = query_vector
    rows = current_session().execute(sql, params).mappings().all()
    results: list[EvidenceChunk] = []
    for row in rows:
        results.append(
            EvidenceChunk(
                chunk_id=row["id"],
                source_id=row["source_id"],
                document_id=row["document_id"],
                text=row["text"],
                citation_anchor=row["citation_anchor"],
                freshness_status=_freshness_for(row["document_id"]),
                score=float(row["score"] or 0.0),
            )
        )
    return results


def _freshness_for(document_id: str) -> str:
    document = get_document(document_id)
    return document.freshness_status if document else "unknown"


# --- SQLite fallback path: in-Python lexical overlap + cosine over JSON embeddings ----------


def _sqlite_lexical_search(context: RequestContext, query: str, allowed_sources: set[str] | None) -> list[EvidenceChunk]:
    query_terms = set(tokenize(query))
    results: list[EvidenceChunk] = []
    for chunk in get_chunks_for_tenant(context):
        # Source filters are applied before scoring so unauthorized chunks never rank.
        if allowed_sources is not None and chunk.source_id not in allowed_sources:
            continue
        terms = tokenize(chunk.text)
        if not terms:
            continue
        overlap = len(query_terms.intersection(terms))
        if overlap:
            results.append(_to_evidence(chunk, overlap / max(len(query_terms), 1)))
    return sorted(results, key=lambda item: item.score, reverse=True)[:_CANDIDATE_LIMIT]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _sqlite_vector_search(context: RequestContext, query_embedding: list[float], allowed_sources: set[str] | None) -> list[EvidenceChunk]:
    results: list[EvidenceChunk] = []
    for chunk in get_chunks_for_tenant(context):
        if allowed_sources is not None and chunk.source_id not in allowed_sources:
            continue
        score = _cosine(query_embedding, chunk.embedding or [])
        if score:
            results.append(_to_evidence(chunk, score))
    return sorted(results, key=lambda item: item.score, reverse=True)[:_CANDIDATE_LIMIT]


# --- Public retrieval API -------------------------------------------------------------------


def lexical_search(context: RequestContext, query: str, options: RetrievalOptions) -> list[EvidenceChunk]:
    allowed_sources = _allowed_source_ids(context, options)
    # Branch on dialect: Postgres uses native FTS/trigram indexes, SQLite uses the portable
    # in-Python fallback so the test suite runs without a database server.
    if _dialect() == "postgresql":
        return _pg_lexical_search(context, query, allowed_sources)
    return _sqlite_lexical_search(context, query, allowed_sources)


def vector_search(context: RequestContext, query: str, options: RetrievalOptions) -> list[EvidenceChunk]:
    allowed_sources = _allowed_source_ids(context, options)
    query_embedding = embed_texts([query])[0]
    if _dialect() == "postgresql":
        return _pg_vector_search(context, query_embedding, allowed_sources)
    return _sqlite_vector_search(context, query_embedding, allowed_sources)


def retrieve_evidence(context: RequestContext, query: str, options: RetrievalOptions | None = None) -> EvidenceSet:
    resolved_options = options or RetrievalOptions()
    logger.info("Retrieval start tenant=%s dialect=%s", context.tenant_id, _dialect())
    try:
        lexical = lexical_search(context, query, resolved_options)
        vector = vector_search(context, query, resolved_options)
    except Exception:
        # Surface the failure for operators but let the caller treat it as no evidence,
        # which yields a safe refusal rather than an unsupported answer.
        logger.error("Retrieval query failed tenant=%s", context.tenant_id, exc_info=True)
        return EvidenceSet(query=query, chunks=[], threshold_met=False)
    ranked = merge_and_rank(lexical, vector, resolved_options.limit)
    # Low-confidence retrieval produces a refusal instead of unsupported generation.
    threshold_met = bool(ranked and ranked[0].score >= resolved_options.min_score)
    logger.info(
        "Retrieval done tenant=%s lexical=%d vector=%d ranked=%d threshold_met=%s",
        context.tenant_id, len(lexical), len(vector), len(ranked), threshold_met,
    )
    return EvidenceSet(query=query, chunks=ranked, threshold_met=threshold_met)

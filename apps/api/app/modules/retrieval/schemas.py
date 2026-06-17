from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceChunk(BaseModel):
    chunk_id: str
    source_id: str
    document_id: str
    text: str
    citation_anchor: str
    freshness_status: str = "fresh"
    score: float = 0.0


class EvidenceSet(BaseModel):
    query: str
    chunks: list[EvidenceChunk] = Field(default_factory=list)
    threshold_met: bool = False
    # Set when the retrieval/index layer raised an error (vs. simply finding nothing), so the
    # orchestrator can return source_unavailable instead of a content refusal.
    retrieval_error: bool = False
    # Set when candidate chunks existed for the tenant but ACL filtering removed all of them,
    # so the orchestrator can return refused_unauthorized instead of refused_no_evidence.
    acl_filtered: bool = False


class RetrievalOptions(BaseModel):
    source_ids: set[str] | None = None
    limit: int = 8
    min_score: float = 0.05

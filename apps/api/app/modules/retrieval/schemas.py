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


class RetrievalOptions(BaseModel):
    source_ids: set[str] | None = None
    limit: int = 8
    min_score: float = 0.05

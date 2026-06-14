from __future__ import annotations

from pydantic import BaseModel

from app.modules.retrieval.schemas import EvidenceSet


class CitationValidationResult(BaseModel):
    valid: bool
    citation_ids: list[str]
    reason: str | None = None


def validate_citations(draft_answer: str, evidence: EvidenceSet, citation_ids: list[str]) -> CitationValidationResult:
    evidence_ids = {chunk.chunk_id for chunk in evidence.chunks}
    if not citation_ids:
        return CitationValidationResult(valid=False, citation_ids=[], reason="No citations provided")
    unknown = [citation_id for citation_id in citation_ids if citation_id not in evidence_ids]
    if unknown:
        return CitationValidationResult(valid=False, citation_ids=citation_ids, reason="Citation not present in retrieved evidence")
    if not draft_answer.strip():
        return CitationValidationResult(valid=False, citation_ids=citation_ids, reason="Empty answer")
    return CitationValidationResult(valid=True, citation_ids=citation_ids)

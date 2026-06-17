from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.modules.llm_gateway.service import CITATION_PREFIX, CITATION_SUFFIX
from app.modules.retrieval.schemas import EvidenceSet

# Matches the inline citation markers the model is instructed to emit, e.g. [[cite:abc-123]].
_CITATION_RE = re.compile(
    re.escape(CITATION_PREFIX) + r"\s*([^\]\s]+)\s*" + re.escape(CITATION_SUFFIX)
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A cited chunk must share at least this many meaningful tokens with the answer text.
# This is a deterministic, offline-safe proxy for "the chunk supports the claim".
_MIN_CLAIM_OVERLAP = 1


class CitationValidationResult(BaseModel):
    valid: bool
    citation_ids: list[str]
    reason: str | None = None
    # Structured per-check outcomes recorded on the trace so operators can see which gate failed.
    checks: dict[str, bool] = Field(default_factory=dict)


def parse_citations(draft_answer: str) -> list[str]:
    """Extract cited chunk IDs from the model output in their first-seen order."""
    seen: list[str] = []
    for match in _CITATION_RE.finditer(draft_answer):
        chunk_id = match.group(1)
        if chunk_id not in seen:
            seen.append(chunk_id)
    return seen


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _strip_markers(text_value: str) -> str:
    return _CITATION_RE.sub(" ", text_value)


def strip_citation_markers(text_value: str) -> str:
    """Remove inline [[cite:...]] markers and tidy whitespace for user-facing display."""
    return re.sub(r"\s+", " ", _strip_markers(text_value)).strip()


def validate_citations(draft_answer: str, evidence: EvidenceSet, citation_ids: list[str]) -> CitationValidationResult:
    """Validate citations beyond mere presence: provenance, claim support, and span resolution.

    Each gate is recorded in `checks` so a failure reason is auditable on the trace, and the
    first failed gate short-circuits to a safe refusal rather than surfacing weakly grounded text.
    """
    checks: dict[str, bool] = {}
    evidence_by_id = {chunk.chunk_id: chunk for chunk in evidence.chunks}

    # 1. Presence: a substantive answer must cite something.
    checks["present"] = bool(citation_ids)
    if not citation_ids:
        return CitationValidationResult(valid=False, citation_ids=[], reason="No citations provided", checks=checks)

    # 2. Provenance: every cited id must come from retrieved evidence, not a hallucinated id.
    unknown = [citation_id for citation_id in citation_ids if citation_id not in evidence_by_id]
    checks["provenance"] = not unknown
    if unknown:
        return CitationValidationResult(
            valid=False, citation_ids=citation_ids,
            reason="Citation not present in retrieved evidence", checks=checks,
        )

    # 3. Empty answers cannot be supported.
    answer_text = _strip_markers(draft_answer).strip()
    checks["non_empty"] = bool(answer_text)
    if not answer_text:
        return CitationValidationResult(valid=False, citation_ids=citation_ids, reason="Empty answer", checks=checks)

    # 4. Span resolution: each cited anchor must resolve to a chunk with a real, non-empty span.
    answer_tokens = _tokens(answer_text)
    span_ok = True
    support_ok = True
    for citation_id in citation_ids:
        chunk = evidence_by_id[citation_id]
        if not chunk.text.strip() or not chunk.citation_anchor.strip():
            span_ok = False
            break
        # 5. Claim support: the cited chunk must share meaningful tokens with the answer text.
        if len(answer_tokens.intersection(_tokens(chunk.text))) < _MIN_CLAIM_OVERLAP:
            support_ok = False
    checks["span"] = span_ok
    if not span_ok:
        return CitationValidationResult(
            valid=False, citation_ids=citation_ids,
            reason="Citation anchor does not resolve to a usable evidence span", checks=checks,
        )
    checks["claim_support"] = support_ok
    if not support_ok:
        return CitationValidationResult(
            valid=False, citation_ids=citation_ids,
            reason="Cited evidence does not support the answer claims", checks=checks,
        )

    return CitationValidationResult(valid=True, citation_ids=citation_ids, checks=checks)

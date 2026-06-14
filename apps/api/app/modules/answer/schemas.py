from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field

from app.modules.retrieval.schemas import EvidenceChunk


class AnswerState(str, Enum):
    answered = "answered"
    partial = "partial"
    clarification_required = "clarification_required"
    refused_no_evidence = "refused_no_evidence"
    refused_unauthorized = "refused_unauthorized"
    source_unavailable = "source_unavailable"
    model_unavailable = "model_unavailable"
    citation_validation_failed = "citation_validation_failed"


class ChatMessageRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    source_filters: set[str] | None = None


class Citation(BaseModel):
    chunk_id: str
    source_id: str
    document_id: str
    citation_anchor: str
    snippet: str


class AnswerResponse(BaseModel):
    answer_id: str
    conversation_id: str
    answer_state: AnswerState
    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    trace_id: str

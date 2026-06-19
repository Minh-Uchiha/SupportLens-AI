from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.modules.answer.schemas import AnswerState
from app.modules.citation.service import parse_citations


DraftState = Literal["answered", "partial", "clarification_required", "refused_no_evidence"]


class AnswerDraft(BaseModel):
    state: DraftState
    answer: str = ""
    clarifying_question: str = ""
    citation_ids: list[str] = Field(default_factory=list)

    @field_validator("answer", "clarifying_question", mode="before")
    @classmethod
    def _string_or_empty(cls, value: object) -> str:
        return value if isinstance(value, str) else ""


class DraftParseResult(BaseModel):
    valid: bool
    draft: AnswerDraft | None = None
    reason: str | None = None
    legacy_clarification: bool = False
    # The model's raw claimed "state" value when JSON decoded but failed validation. Pure
    # telemetry so failure traces show what the model tried to say (e.g. an unsupported state
    # or a clarification carrying citations) rather than just "draft_parse: False".
    raw_state: str | None = None


_CLARIFY_RE = re.compile(r"^\s*clarify:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)
_MIXED_MARKER_RE = re.compile(r"\b(clarify|partial):", re.IGNORECASE)


def _decode_first_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return value if isinstance(value, dict) else None
    return None


def _clean_legacy_clarification(text: str) -> DraftParseResult | None:
    if parse_citations(text) or "partial:" in text.lower():
        return None
    match = _CLARIFY_RE.match(text)
    if not match:
        return None
    question = match.group(1).strip()
    if not question or "\n" in question:
        return None
    return DraftParseResult(
        valid=True,
        draft=AnswerDraft(state=AnswerState.clarification_required.value, clarifying_question=question),
        legacy_clarification=True,
    )


def parse_answer_draft(text: str) -> DraftParseResult:
    """Parse the model's answer draft.

    The primary contract is a single JSON object. A very narrow legacy CLARIFY-only
    fallback is kept so older local prompts fail softly, but mixed marker responses are
    intentionally rejected instead of being treated as real clarifications.
    """
    legacy = _clean_legacy_clarification(text)
    if legacy is not None:
        return legacy

    value = _decode_first_json_object(text)
    if value is None:
        reason = "Mixed marker response is not valid structured output" if _MIXED_MARKER_RE.search(text) else "No JSON object found"
        return DraftParseResult(valid=False, reason=reason)

    raw_state = value.get("state") if isinstance(value.get("state"), str) else None

    try:
        draft = AnswerDraft.model_validate(value)
    except ValidationError as exc:
        return DraftParseResult(valid=False, reason=f"Invalid answer draft: {exc.errors()[0]['msg']}", raw_state=raw_state)

    state = AnswerState(draft.state)
    answer = draft.answer.strip()
    clarifying_question = draft.clarifying_question.strip()
    citation_ids = [item.strip() for item in draft.citation_ids if item.strip()]
    draft = draft.model_copy(update={"answer": answer, "clarifying_question": clarifying_question, "citation_ids": citation_ids})
    if _MIXED_MARKER_RE.search(answer) or _MIXED_MARKER_RE.search(clarifying_question):
        return DraftParseResult(valid=False, reason="Draft text contains legacy state markers", raw_state=raw_state)

    if state == AnswerState.clarification_required:
        if not clarifying_question:
            return DraftParseResult(valid=False, reason="Clarification draft missing clarifying_question", raw_state=raw_state)
        if answer or citation_ids:
            return DraftParseResult(valid=False, reason="Clarification draft included answer text or citations", raw_state=raw_state)
        return DraftParseResult(valid=True, draft=draft, raw_state=raw_state)

    if state in {AnswerState.answered, AnswerState.partial}:
        if not answer:
            return DraftParseResult(valid=False, reason="Substantive draft missing answer", raw_state=raw_state)
        if not citation_ids:
            return DraftParseResult(valid=False, reason="Substantive draft missing citation_ids", raw_state=raw_state)
        return DraftParseResult(valid=True, draft=draft, raw_state=raw_state)

    if state == AnswerState.refused_no_evidence:
        if not answer:
            return DraftParseResult(valid=False, reason="Refusal draft missing answer", raw_state=raw_state)
        return DraftParseResult(valid=True, draft=draft, raw_state=raw_state)

    return DraftParseResult(valid=False, reason=f"Unsupported draft state: {draft.state}", raw_state=raw_state)

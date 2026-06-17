from __future__ import annotations

from app.modules.answer.prompts import build_grounded_prompt
from app.modules.answer.schemas import AnswerResponse, AnswerState, ChatMessageRequest, Citation
from app.modules.auth_policy.schemas import RequestContext
from app.modules.citation.service import parse_citations, strip_citation_markers, validate_citations
from app.modules.conversation.schemas import ConversationCreate
from app.modules.conversation.service import add_message, conversation_context, create_conversation, store_answer
from app.modules.llm_gateway.service import call_model
from app.modules.retrieval.schemas import RetrievalOptions
from app.modules.retrieval.service import retrieve_evidence
from app.modules.telemetry.service import add_trace_stage, finish_trace, record_usage, start_trace

# Markers the prompt asks the model to lead with so partial answers and clarifying
# questions can be classified deterministically.
_CLARIFY_MARKER = "clarify:"
_PARTIAL_MARKER = "partial:"

# Safe, content-free user-facing messages for each non-answered terminal state.
_MESSAGES = {
    AnswerState.refused_no_evidence: "I could not find enough authorized evidence to answer that question.",
    AnswerState.refused_unauthorized: "I cannot answer because you are not authorized to access the relevant sources.",
    AnswerState.source_unavailable: "I could not search the knowledge sources right now. Please try again shortly.",
    AnswerState.model_unavailable: "Answer generation is temporarily unavailable.",
    AnswerState.citation_validation_failed: "I cannot provide a supported answer because citation validation failed.",
}


def is_clarification(answer_text: str) -> bool:
    return answer_text.strip().lower().startswith(_CLARIFY_MARKER)


def classify_answer_state(answer_text: str, validation_valid: bool) -> AnswerState:
    """Classify a substantive model answer into an answer state.

    Clarifying questions are handled before this is called (they carry no citations by
    design). Here, citation validation gates everything: an answer that fails validation
    can never be answered/partial. A PARTIAL marker downgrades a valid answer to partial.
    """
    if not validation_valid:
        return AnswerState.citation_validation_failed
    if answer_text.strip().lower().startswith(_PARTIAL_MARKER):
        return AnswerState.partial
    return AnswerState.answered


def _citations_from_evidence(citation_ids: list[str], evidence_chunks) -> list[Citation]:
    by_id = {chunk.chunk_id: chunk for chunk in evidence_chunks}
    citations: list[Citation] = []
    for citation_id in citation_ids:
        chunk = by_id[citation_id]
        citations.append(Citation(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            document_id=chunk.document_id,
            citation_anchor=chunk.citation_anchor,
            snippet=chunk.text[:300],
        ))
    return citations


def _terminal(context, conversation_id, message_id, trace_id, state: AnswerState, evidence_chunks=None) -> AnswerResponse:
    """Persist a non-answered terminal state with a safe message and no citations."""
    answer_text = _MESSAGES[state]
    stored = store_answer(context, conversation_id, message_id, state.value, answer_text, trace_id, [])
    finish_trace(trace_id, state.value)
    return AnswerResponse(
        answer_id=stored.id,
        conversation_id=conversation_id,
        answer_state=state,
        answer_text=answer_text,
        trace_id=trace_id,
        evidence=evidence_chunks or [],
    )


def generate_answer(context: RequestContext, request: ChatMessageRequest) -> AnswerResponse:
    conversation = create_conversation(context, ConversationCreate(title=request.message[:60])) if request.conversation_id is None else None
    conversation_id = conversation.id if conversation else request.conversation_id
    assert conversation_id is not None
    trace = start_trace(context, conversation_id)
    user_message = add_message(context, conversation_id, "user", request.message)

    evidence = retrieve_evidence(context, request.message, RetrievalOptions(source_ids=request.source_filters))
    add_trace_stage(trace.id, "retrieval", {
        "count": len(evidence.chunks),
        "threshold_met": evidence.threshold_met,
        "retrieval_error": evidence.retrieval_error,
        "acl_filtered": evidence.acl_filtered,
    })

    if evidence.retrieval_error:
        # Index/query failure: never fabricate; report the outage so it is distinct from a refusal.
        return _terminal(context, conversation_id, user_message.id, trace.id, AnswerState.source_unavailable)
    if not evidence.threshold_met:
        # Distinguish "you cannot access the sources" from "nothing relevant is indexed".
        state = AnswerState.refused_unauthorized if evidence.acl_filtered else AnswerState.refused_no_evidence
        return _terminal(context, conversation_id, user_message.id, trace.id, state)

    prompt = build_grounded_prompt(request.message, conversation_context(context, conversation_id), evidence)
    model_result = call_model(prompt)
    add_trace_stage(trace.id, "model", {
        "model": model_result.model,
        "unavailable": model_result.unavailable,
        "used_fallback": model_result.used_fallback,
        "latency_ms": model_result.latency_ms,
        "attempts": model_result.attempts,
    })
    if model_result.unavailable:
        return _terminal(context, conversation_id, user_message.id, trace.id, AnswerState.model_unavailable, evidence.chunks)

    # A clarifying question legitimately carries no citations, so classify it before
    # citation validation (which would otherwise fail it for having no citations).
    if is_clarification(model_result.text):
        display_text = strip_citation_markers(model_result.text)
        add_trace_stage(trace.id, "citation_validation", {"valid": True, "reason": "clarification", "checks": {}})
        stored = store_answer(context, conversation_id, user_message.id, AnswerState.clarification_required.value, display_text, trace.id, [])
        finish_trace(trace.id, AnswerState.clarification_required.value)
        return AnswerResponse(
            answer_id=stored.id,
            conversation_id=conversation_id,
            answer_state=AnswerState.clarification_required,
            answer_text=display_text,
            evidence=evidence.chunks,
            trace_id=trace.id,
        )

    # Parse the chunks the model actually cited and validate them against retrieved evidence.
    citation_ids = parse_citations(model_result.text)
    validation = validate_citations(model_result.text, evidence, citation_ids)
    add_trace_stage(trace.id, "citation_validation", {"valid": validation.valid, "reason": validation.reason, "checks": validation.checks})
    state = classify_answer_state(model_result.text, validation.valid)

    if state == AnswerState.citation_validation_failed:
        return _terminal(context, conversation_id, user_message.id, trace.id, state, evidence.chunks)

    citations = _citations_from_evidence(validation.citation_ids, evidence.chunks)
    # Citations are returned as structured objects, so strip the inline markers from the
    # user-facing text rather than showing raw [[cite:...]] tokens.
    display_text = strip_citation_markers(model_result.text)
    stored = store_answer(context, conversation_id, user_message.id, state.value, display_text, trace.id, [item.chunk_id for item in citations])
    record_usage(context, "retrieved_chunks", len(evidence.chunks))
    finish_trace(trace.id, state.value)
    return AnswerResponse(
        answer_id=stored.id,
        conversation_id=conversation_id,
        answer_state=state,
        answer_text=display_text,
        citations=citations,
        evidence=evidence.chunks,
        trace_id=trace.id,
    )

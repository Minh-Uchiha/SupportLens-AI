from __future__ import annotations

from app.modules.answer.drafts import parse_answer_draft
from app.modules.answer.prompts import build_grounded_prompt
from app.modules.answer.schemas import AnswerResponse, AnswerState, ChatMessageRequest, Citation
from app.modules.auth_policy.schemas import RequestContext
from app.modules.citation.service import validate_citations
from app.modules.conversation.schemas import ConversationCreate
from app.modules.conversation.service import add_message, conversation_context, create_conversation, store_answer
from app.modules.llm_gateway.embeddings import current_embedding_model
from app.modules.llm_gateway.service import call_model
from app.modules.retrieval.schemas import RetrievalOptions
from app.modules.retrieval.service import retrieve_evidence
from app.modules.telemetry.service import add_trace_stage, finish_trace, record_usage, start_trace

# Safe, content-free user-facing messages for each non-answered terminal state.
_MESSAGES = {
    AnswerState.refused_no_evidence: "I could not find enough authorized evidence to answer that question.",
    AnswerState.refused_unauthorized: "I cannot answer because you are not authorized to access the relevant sources.",
    AnswerState.source_unavailable: "I could not search the knowledge sources right now. Please try again shortly.",
    AnswerState.model_unavailable: "Answer generation is temporarily unavailable.",
    AnswerState.citation_validation_failed: "I cannot provide a supported answer because citation validation failed.",
}


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
    prior_context = conversation_context(context, conversation_id)
    user_message = add_message(context, conversation_id, "user", request.message)

    evidence = retrieve_evidence(context, request.message, RetrievalOptions(source_ids=request.source_filters))
    add_trace_stage(trace.id, "retrieval", {
        "count": len(evidence.chunks),
        "threshold_met": evidence.threshold_met,
        "retrieval_error": evidence.retrieval_error,
        "acl_filtered": evidence.acl_filtered,
        "embedding_model": current_embedding_model(),
        "chunks": [
            {"chunk_id": chunk.chunk_id, "citation_anchor": chunk.citation_anchor, "score": chunk.score}
            for chunk in evidence.chunks
        ],
    })

    if evidence.retrieval_error:
        # Index/query failure: never fabricate; report the outage so it is distinct from a refusal.
        return _terminal(context, conversation_id, user_message.id, trace.id, AnswerState.source_unavailable)
    if not evidence.threshold_met:
        # Distinguish "you cannot access the sources" from "nothing relevant is indexed".
        state = AnswerState.refused_unauthorized if evidence.acl_filtered else AnswerState.refused_no_evidence
        return _terminal(context, conversation_id, user_message.id, trace.id, state)

    prompt = build_grounded_prompt(request.message, prior_context, evidence)
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

    draft_result = parse_answer_draft(model_result.text)
    if not draft_result.valid or draft_result.draft is None:
        add_trace_stage(trace.id, "citation_validation", {
            "valid": False,
            "reason": draft_result.reason or "Invalid model answer draft",
            "checks": {"draft_parse": False},
            "raw_state": draft_result.raw_state,
        })
        return _terminal(context, conversation_id, user_message.id, trace.id, AnswerState.citation_validation_failed, evidence.chunks)

    draft = draft_result.draft
    draft_state = AnswerState(draft.state)
    if draft_state == AnswerState.clarification_required:
        display_text = draft.clarifying_question
        add_trace_stage(trace.id, "citation_validation", {
            "valid": True,
            "reason": "clarification",
            "checks": {"draft_parse": True},
            "legacy_clarification": draft_result.legacy_clarification,
        })
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

    if draft_state == AnswerState.refused_no_evidence:
        add_trace_stage(trace.id, "citation_validation", {
            "valid": True,
            "reason": "model_refused_no_evidence",
            "checks": {"draft_parse": True},
        })
        stored = store_answer(context, conversation_id, user_message.id, AnswerState.refused_no_evidence.value, draft.answer, trace.id, [])
        finish_trace(trace.id, AnswerState.refused_no_evidence.value)
        return AnswerResponse(
            answer_id=stored.id,
            conversation_id=conversation_id,
            answer_state=AnswerState.refused_no_evidence,
            answer_text=draft.answer,
            evidence=evidence.chunks,
            trace_id=trace.id,
        )

    validation = validate_citations(draft.answer, evidence, draft.citation_ids)
    add_trace_stage(trace.id, "citation_validation", {
        "valid": validation.valid,
        "reason": validation.reason,
        "checks": {"draft_parse": True, **validation.checks},
        "draft_state": draft.state,
        "citation_ids": draft.citation_ids,
    })
    if not validation.valid:
        return _terminal(context, conversation_id, user_message.id, trace.id, AnswerState.citation_validation_failed, evidence.chunks)

    citations = _citations_from_evidence(validation.citation_ids, evidence.chunks)
    display_text = draft.answer
    stored = store_answer(context, conversation_id, user_message.id, draft_state.value, display_text, trace.id, [item.chunk_id for item in citations])
    record_usage(context, "retrieved_chunks", len(evidence.chunks))
    finish_trace(trace.id, draft_state.value)
    return AnswerResponse(
        answer_id=stored.id,
        conversation_id=conversation_id,
        answer_state=draft_state,
        answer_text=display_text,
        citations=citations,
        evidence=evidence.chunks,
        trace_id=trace.id,
    )

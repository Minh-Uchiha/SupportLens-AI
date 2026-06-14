from __future__ import annotations

from app.modules.answer.prompts import build_grounded_prompt
from app.modules.answer.schemas import AnswerResponse, AnswerState, ChatMessageRequest, Citation
from app.modules.auth_policy.schemas import RequestContext
from app.modules.citation.service import validate_citations
from app.modules.conversation.schemas import ConversationCreate
from app.modules.conversation.service import add_message, conversation_context, create_conversation, store_answer
from app.modules.llm_gateway.service import call_model
from app.modules.retrieval.schemas import RetrievalOptions
from app.modules.retrieval.service import retrieve_evidence
from app.modules.telemetry.service import add_trace_stage, finish_trace, record_usage, start_trace


def classify_answer_state(has_evidence: bool, validation_valid: bool, model_unavailable: bool = False) -> AnswerState:
    if model_unavailable:
        return AnswerState.model_unavailable
    if not has_evidence:
        return AnswerState.refused_no_evidence
    if not validation_valid:
        return AnswerState.citation_validation_failed
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


def generate_answer(context: RequestContext, request: ChatMessageRequest) -> AnswerResponse:
    conversation = create_conversation(context, ConversationCreate(title=request.message[:60])) if request.conversation_id is None else None
    conversation_id = conversation.id if conversation else request.conversation_id
    assert conversation_id is not None
    trace = start_trace(context, conversation_id)
    user_message = add_message(context, conversation_id, "user", request.message)

    evidence = retrieve_evidence(context, request.message, RetrievalOptions(source_ids=request.source_filters))
    add_trace_stage(trace.id, "retrieval", {"count": len(evidence.chunks), "threshold_met": evidence.threshold_met})

    if not evidence.threshold_met:
        state = AnswerState.refused_no_evidence
        answer_text = "I could not find enough authorized evidence to answer that question."
        stored = store_answer(context, conversation_id, user_message.id, state.value, answer_text, trace.id, [])
        finish_trace(trace.id, state.value)
        return AnswerResponse(answer_id=stored.id, conversation_id=conversation_id, answer_state=state, answer_text=answer_text, trace_id=trace.id)

    prompt = build_grounded_prompt(request.message, conversation_context(context, conversation_id), evidence)
    model_result = call_model(prompt)
    add_trace_stage(trace.id, "model", {"model": model_result.model, "unavailable": model_result.unavailable})
    if model_result.unavailable:
        state = AnswerState.model_unavailable
        answer_text = "Answer generation is temporarily unavailable."
        stored = store_answer(context, conversation_id, user_message.id, state.value, answer_text, trace.id, [])
        finish_trace(trace.id, state.value)
        return AnswerResponse(answer_id=stored.id, conversation_id=conversation_id, answer_state=state, answer_text=answer_text, trace_id=trace.id, evidence=evidence.chunks)

    citation_ids = [evidence.chunks[0].chunk_id]
    validation = validate_citations(model_result.text, evidence, citation_ids)
    add_trace_stage(trace.id, "citation_validation", {"valid": validation.valid, "reason": validation.reason})
    state = classify_answer_state(True, validation.valid, model_result.unavailable)
    answer_text = model_result.text if validation.valid else "I cannot provide a supported answer because citation validation failed."
    citations = _citations_from_evidence(citation_ids, evidence.chunks) if validation.valid else []
    stored = store_answer(context, conversation_id, user_message.id, state.value, answer_text, trace.id, [item.chunk_id for item in citations])
    record_usage(context, "retrieved_chunks", len(evidence.chunks))
    finish_trace(trace.id, state.value)
    return AnswerResponse(
        answer_id=stored.id,
        conversation_id=conversation_id,
        answer_state=state,
        answer_text=answer_text,
        citations=citations,
        evidence=evidence.chunks,
        trace_id=trace.id,
    )

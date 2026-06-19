from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.modules.answer.drafts import parse_answer_draft
from app.modules.answer.schemas import AnswerState
from app.modules.citation.service import parse_citations, strip_citation_markers, validate_citations
from app.modules.evaluation.datasets import load_launch_dataset
from app.modules.llm_gateway import litellm_client
from app.modules.llm_gateway.litellm_client import ModelCallError
from app.modules.llm_gateway.service import CITATION_PREFIX, CITATION_SUFFIX, ModelResult, PromptBundle, call_model
from app.modules.retrieval.schemas import EvidenceChunk, EvidenceSet


def _seed_source(client, admin_headers, name="Runbook", text=None):
    text = text or (
        "Error SL-429 means the tenant has exceeded support rate limits. Resolve it by "
        "checking usage and retrying after the backoff window."
    )
    source = client.post(
        "/v1/admin/sources",
        json={"type": "inline", "name": name, "connection_ref": text},
        headers=admin_headers,
    )
    assert source.status_code == 200
    source_id = source.json()["id"]
    sync = client.post(f"/v1/admin/sources/{source_id}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    assert sync.status_code == 200
    return source_id


def _evidence_chunk(chunk_id="chunk-1", text="Error SL-429 means the tenant exceeded support rate limits."):
    return EvidenceChunk(
        chunk_id=chunk_id, source_id="src-1", document_id="doc-1",
        text=text, citation_anchor="Runbook#chunk-1", score=0.9,
    )


# --- Answer state coverage (via the live API) ----------------------------------------------


def test_answered_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.answered.value
    assert body["citations"]
    assert CITATION_PREFIX not in body["answer_text"]


def test_refused_no_evidence_state(client, user_headers):
    body = client.post("/v1/chat/messages", json={"message": "completely absent unrelated topic"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.refused_no_evidence.value
    assert body["citations"] == []


def test_model_unavailable_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    body = client.post("/v1/chat/messages", json={"message": "simulate_model_unavailable SL-429"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.model_unavailable.value
    assert body["citations"] == []


def test_source_unavailable_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    # An index/query failure must surface as source_unavailable, not a content refusal.
    with patch("app.modules.answer.service.retrieve_evidence") as mock_retrieve:
        mock_retrieve.return_value = EvidenceSet(query="x", chunks=[], threshold_met=False, retrieval_error=True)
        body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.source_unavailable.value


def test_refused_unauthorized_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    with patch("app.modules.answer.service.retrieve_evidence") as mock_retrieve:
        mock_retrieve.return_value = EvidenceSet(query="x", chunks=[], threshold_met=False, acl_filtered=True)
        body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.refused_unauthorized.value


def test_partial_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    chunk_text = "Error SL-429 means the tenant has exceeded support rate limits."

    def fake_call_model(prompt: PromptBundle, model_options=None):
        chunk_id = prompt.evidence.chunks[0].chunk_id
        return ModelResult(text=json.dumps({
            "state": "partial",
            "answer": chunk_text,
            "clarifying_question": "",
            "citation_ids": [chunk_id],
        }))

    with patch("app.modules.answer.service.call_model", side_effect=fake_call_model):
        body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.partial.value
    assert body["citations"]


def test_clarification_required_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)

    def fake_call_model(prompt: PromptBundle, model_options=None):
        return ModelResult(text=json.dumps({
            "state": "clarification_required",
            "answer": "",
            "clarifying_question": "Which environment are you asking about?",
            "citation_ids": [],
        }))

    with patch("app.modules.answer.service.call_model", side_effect=fake_call_model):
        body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.clarification_required.value
    # Clarifying questions carry no citations and must not fail citation validation.
    assert body["citations"] == []


def test_citation_validation_failed_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)

    def fake_call_model(prompt: PromptBundle, model_options=None):
        return ModelResult(text=json.dumps({
            "state": "answered",
            "answer": "SL-429 is resolved by waiting.",
            "clarifying_question": "",
            "citation_ids": ["not-a-real-chunk"],
        }))

    with patch("app.modules.answer.service.call_model", side_effect=fake_call_model):
        body = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers).json()
    assert body["answer_state"] == AnswerState.citation_validation_failed.value
    assert body["citations"] == []


# --- Citation validation unit coverage ------------------------------------------------------


def test_parse_answer_draft_accepts_substantive_json():
    draft = parse_answer_draft(json.dumps({
        "state": "answered",
        "answer": "Reset the password.",
        "clarifying_question": "",
        "citation_ids": ["chunk-1"],
    }))
    assert draft.valid is True
    assert draft.draft is not None
    assert draft.draft.citation_ids == ["chunk-1"]


def test_parse_answer_draft_rejects_mixed_marker_response():
    draft = parse_answer_draft("CLARIFY: Which employee type? PARTIAL: Exempt employees get flexible PTO.")
    assert draft.valid is False
    assert "Mixed marker" in (draft.reason or "")


def test_parse_answer_draft_rejects_json_with_legacy_markers():
    draft = parse_answer_draft(json.dumps({
        "state": "answered",
        "answer": "CLARIFY: Which employee type? PARTIAL: Exempt employees get flexible PTO.",
        "clarifying_question": "",
        "citation_ids": ["chunk-1"],
    }))
    assert draft.valid is False


def test_parse_answer_draft_rejects_anchor_style_citation_without_json():
    draft = parse_answer_draft("Answer [[cite:Adobe break policy#chunk-8]]")
    assert draft.valid is False


def test_select_prompt_chunks_drops_low_relevance_noise():
    from app.modules.answer.prompts import PROMPT_MAX_CHUNKS, select_prompt_chunks

    # One clearly-relevant chunk plus low-score noise: only the relevant chunk should be shown.
    chunks = [
        _evidence_chunk(chunk_id="top", text="Minh's favorite sport is badminton."),
        EvidenceChunk(chunk_id="noise1", source_id="s", document_id="d", text="unrelated policy text", citation_anchor="P#1", score=0.1),
        EvidenceChunk(chunk_id="noise2", source_id="s", document_id="d", text="more unrelated text", citation_anchor="P#2", score=0.05),
    ]
    chunks[0] = chunks[0].model_copy(update={"score": 2.0})
    evidence = EvidenceSet(query="q", chunks=chunks, threshold_met=True)
    selected = select_prompt_chunks(evidence)
    assert [c.chunk_id for c in selected] == ["top"]
    assert len(selected) <= PROMPT_MAX_CHUNKS


def test_select_prompt_chunks_keeps_top_when_scores_are_close():
    from app.modules.answer.prompts import PROMPT_MAX_CHUNKS, select_prompt_chunks

    chunks = [
        EvidenceChunk(chunk_id=f"c{i}", source_id="s", document_id="d", text=f"text {i}", citation_anchor=f"A#{i}", score=2.0 - i * 0.1)
        for i in range(6)
    ]
    evidence = EvidenceSet(query="q", chunks=chunks, threshold_met=True)
    selected = select_prompt_chunks(evidence)
    # Close scores stay above the relative cutoff, but the count is capped.
    assert len(selected) == PROMPT_MAX_CHUNKS
    assert selected[0].chunk_id == "c0"


def test_parse_answer_draft_records_raw_state_on_invalid_draft():
    # A clarification that smuggles in citations is invalid, but the failure trace should still
    # capture what the model claimed so the failure mode is observable.
    draft = parse_answer_draft(json.dumps({
        "state": "clarification_required",
        "answer": "",
        "clarifying_question": "Which environment?",
        "citation_ids": ["chunk-1"],
    }))
    assert draft.valid is False
    assert draft.raw_state == "clarification_required"


def test_parse_citations_extracts_unique_ids_in_order():
    text = f"A {CITATION_PREFIX}c1{CITATION_SUFFIX} B {CITATION_PREFIX}c2{CITATION_SUFFIX} {CITATION_PREFIX}c1{CITATION_SUFFIX}"
    assert parse_citations(text) == ["c1", "c2"]


def test_strip_citation_markers_cleans_text():
    text = f"Reset the password. {CITATION_PREFIX}c1{CITATION_SUFFIX}"
    assert strip_citation_markers(text) == "Reset the password."


def test_validate_citations_presence_failure():
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk()], threshold_met=True)
    result = validate_citations("some answer", evidence, [])
    assert result.valid is False
    assert result.checks["present"] is False


def test_validate_citations_provenance_failure():
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk()], threshold_met=True)
    result = validate_citations("answer text", evidence, ["unknown-chunk"])
    assert result.valid is False
    assert result.checks["provenance"] is False


def test_validate_citations_claim_support_failure():
    # The answer shares no meaningful tokens with the cited chunk.
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk(text="alpha beta gamma delta")], threshold_met=True)
    result = validate_citations("zzz qqq wholly unrelated wording", evidence, ["chunk-1"])
    assert result.valid is False
    assert result.checks["claim_support"] is False


def test_validate_citations_span_failure():
    # Empty citation anchor cannot resolve to a usable span.
    chunk = EvidenceChunk(chunk_id="chunk-1", source_id="s", document_id="d", text="some text", citation_anchor="  ", score=0.5)
    evidence = EvidenceSet(query="q", chunks=[chunk], threshold_met=True)
    result = validate_citations("some text answer", evidence, ["chunk-1"])
    assert result.valid is False
    assert result.checks["span"] is False


def test_validate_citations_success():
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk(text="tenant exceeded rate limits")], threshold_met=True)
    result = validate_citations("the tenant exceeded rate limits", evidence, ["chunk-1"])
    assert result.valid is True
    assert all(result.checks.values())


# --- LiteLLM client: timeout / retry / fallback --------------------------------------------


def _settings(**overrides) -> Settings:
    base = dict(local_deterministic_llm=False, llm_max_retries=2, llm_retry_backoff_seconds=0.0)
    base.update(overrides)
    return Settings(**base)


def test_litellm_complete_success(monkeypatch):
    calls = {"n": 0, "payload": None}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "hello from model"}}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            calls["n"] += 1
            calls["payload"] = k["json"]
            return _Resp()

    monkeypatch.setattr(litellm_client, "get_settings", lambda: _settings())
    monkeypatch.setattr(httpx, "Client", _Client)
    assert litellm_client.complete([{"role": "user", "content": "hi"}]) == "hello from model"
    assert calls["n"] == 1
    assert calls["payload"]["temperature"] == 0.0
    assert calls["payload"]["max_tokens"] == 450
    # Conservative stop sequences bound runaway repeated-marker output.
    assert calls["payload"]["stop"] == ["\nCLARIFY:", "\nPARTIAL:", "\n\n\n"]


def test_litellm_omits_stop_when_disabled(monkeypatch):
    calls = {"payload": None}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            calls["payload"] = k["json"]
            return _Resp()

    monkeypatch.setattr(litellm_client, "get_settings", lambda: _settings(llm_stop_sequences=[]))
    monkeypatch.setattr(httpx, "Client", _Client)
    litellm_client.complete([{"role": "user", "content": "hi"}])
    assert "stop" not in calls["payload"]


def test_litellm_complete_retries_transient_then_fails(monkeypatch):
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            calls["n"] += 1
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(litellm_client, "get_settings", lambda: _settings())
    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(litellm_client.time, "sleep", lambda *_: None)
    with pytest.raises(ModelCallError):
        litellm_client.complete([{"role": "user", "content": "hi"}])
    # max_retries=2 -> 3 attempts total for a transient error.
    assert calls["n"] == 3


def test_litellm_complete_does_not_retry_client_error(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 400

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            calls["n"] += 1
            raise httpx.HTTPStatusError("bad request", request=None, response=_Resp())

    monkeypatch.setattr(litellm_client, "get_settings", lambda: _settings())
    monkeypatch.setattr(httpx, "Client", _Client)
    with pytest.raises(ModelCallError):
        litellm_client.complete([{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


def test_call_model_falls_back_to_deterministic_on_outage(monkeypatch):
    monkeypatch.setattr("app.modules.llm_gateway.service.get_settings", lambda: _settings())

    def _raise(_messages, _model_options=None):
        raise ModelCallError("down")

    monkeypatch.setattr("app.modules.llm_gateway.service.complete", _raise)
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk()], threshold_met=True)
    prompt = PromptBundle(question="how to fix SL-429", evidence=evidence, instructions="", messages=[])
    result = call_model(prompt)
    assert result.unavailable is False
    assert result.used_fallback is True
    assert result.model == "deterministic-local"
    draft = parse_answer_draft(result.text)
    assert draft.valid is True
    assert draft.draft is not None
    assert draft.draft.citation_ids == ["chunk-1"]


def test_call_model_uses_litellm_when_available(monkeypatch):
    monkeypatch.setattr("app.modules.llm_gateway.service.get_settings", lambda: _settings(litellm_model="m1"))
    monkeypatch.setattr("app.modules.llm_gateway.service.complete", lambda messages, model_options=None: "model answer")
    evidence = EvidenceSet(query="q", chunks=[_evidence_chunk()], threshold_met=True)
    prompt = PromptBundle(question="how to fix SL-429", evidence=evidence, instructions="", messages=[])
    result = call_model(prompt)
    assert result.text == "model answer"
    assert result.model == "m1"
    assert result.used_fallback is False
    assert result.latency_ms is not None


# --- Launch dataset loader ------------------------------------------------------------------


def test_launch_dataset_loads_scenarios():
    dataset = load_launch_dataset()
    assert dataset.name
    assert len(dataset.scenarios) >= 4
    states = {scenario.expected_state for scenario in dataset.scenarios}
    assert "answered" in states
    assert "refused_no_evidence" in states
    assert "clarification_required" in states
    # Every scenario declares whether a citation is expected.
    assert all(isinstance(scenario.expected_citation, bool) for scenario in dataset.scenarios)

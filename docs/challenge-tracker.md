# SupportLens Challenge Tracker

Living record of issues found while building and manually testing the chat flow, plus the
status and verification of each fix. Add a new row to the summary table when a challenge is
identified, then keep its detail section updated as it moves toward resolved.

**Status legend:** ✅ Resolved · 🟡 In progress · 🔴 Open · ⚪ Accepted (won't fix / external limit)

## Test environment

- Docker Compose: Postgres (pgvector), Redis, Ollama, LiteLLM, API, web, ingestion/evaluation workers.
- LiteLLM routes `supportlens-local` → Ollama `llama3.2:1b` (lightweight local model).
- Source under test: Adobe vacation/holidays page
  `https://benefits.adobe.com/us/time-off/vacation-and-paid-holidays`, plus an inline "Minh hobby" source.
- Driving questions: when an Adobe employee named Minh can take a break in 2026; what Minh's favorite/disliked sport is.
- Expected behavior: a cited answer grounded in the evidence, or one clear clarifying question — never repeated/mixed control markers, never an unsupported claim.

## Summary

| # | Challenge | Status | Last updated |
|---|-----------|--------|--------------|
| 1 | Embeddings configured but not installed | ✅ Resolved | 2026-06-18 |
| 2 | Lexical retrieval returned zero candidates | ✅ Resolved | 2026-06-18 |
| 3 | Small model mixed answer states (`CLARIFY:`/`PARTIAL:`) | ✅ Resolved | 2026-06-18 |
| 4 | Citation identifiers were wrong (anchor vs UUID) | ✅ Resolved | 2026-06-18 |
| 5 | Clarification-prefixed text skipped citation validation | ✅ Resolved | 2026-06-18 |
| 6 | Prompt context duplicated the current question | ✅ Resolved | 2026-06-18 |
| 7 | UI rendering made mixed states confusing | ✅ Resolved | 2026-06-18 |
| 8 | Weak model produced empty/parroted answers → `citation_validation_failed` | ✅ Resolved | 2026-06-18 |
| 9 | `llama3.2:1b` comprehension limits on nuanced questions | ⚪ Accepted | 2026-06-18 |
| 10 | Integration tests flake when a live LiteLLM is reachable | 🔴 Open | 2026-06-18 |
| 11 | Off-topic questions answered instead of refused | ✅ Resolved | 2026-06-18 |

---

## 1. Embeddings configured but not installed — ✅ Resolved

**Problem.** `embedding_model` in [config.py](../apps/api/app/core/config.py) names the desired model,
but it is only used when `sentence-transformers` is installed and loads successfully. Earlier images
installed the base API package without the `embeddings` extra, so indexed chunks used
`deterministic-hash-fallback` vectors — stable but not semantically meaningful.

**Fix.** Compose images now install the embeddings extra:
- API image: `pip install --no-cache-dir -e '.[embeddings]'`
- Worker image: `pip install --no-cache-dir -e './apps/api[embeddings]'`

**Verification.** After resync, DB chunks report `sentence-transformers/all-MiniLM-L6-v2`. Confirmed
on the live stack: the Adobe source synced to 10 chunks, all with real embedding vectors.

> Note: chunks created before this change must be re-embedded or resynced, or they keep their
> `deterministic-hash-fallback` vectors.

## 2. Lexical retrieval returned zero candidates — ✅ Resolved

**Problem.** Postgres full-text search returned zero rows for natural-language questions that mix
user context with policy terms (e.g. "Minh … break in 2026"); `plainto_tsquery` required every
term to match. Retrieval was effectively vector-only.

**Fix.** Hybrid retrieval in [retrieval/service.py](../apps/api/app/modules/retrieval/service.py) and
[ranking.py](../apps/api/app/modules/retrieval/ranking.py): `websearch_to_tsquery` + an OR-token
fallback (`to_tsquery` over de-duplicated, stop-word-filtered tokens) + a trigram `similarity`
floor, merged with vector candidates via min-max-normalized score summation.

**Verification.** Live trace for the Adobe question shows the company-break chunk ranked #1
(score 2.0) with 2026 holidays, global wellbeing days, and exempt/non-exempt/intern caveats in the
top results; lexical candidates are non-zero.

## 3. Small model mixed answer states — ✅ Resolved

**Problem.** The old prompt asked the model to use `CLARIFY:` / `PARTIAL:` markers; `llama3.2:1b`
turned this into pattern completion and emitted repeated `CLARIFY: … PARTIAL: …` sub-responses.

**Fix.** Replaced the marker protocol with a strict JSON draft contract (`state`, `answer`,
`clarifying_question`, `citation_ids`) in [prompts.py](../apps/api/app/modules/answer/prompts.py),
a defensive parser in [drafts.py](../apps/api/app/modules/answer/drafts.py) that rejects mixed-marker
text, and bounded generation (`temperature: 0`, `max_tokens: 450`, conservative stop sequences) in
[config.py](../apps/api/app/core/config.py) / [litellm_client.py](../apps/api/app/modules/llm_gateway/litellm_client.py).

**Verification.** Across live runs, no response contained repeated/mixed markers; each is exactly one
state. Unit tests cover marker rejection and the stop-sequence payload.

## 4. Citation identifiers were wrong — ✅ Resolved

**Problem.** The model cited human-readable anchors (`Adobe break policy#chunk-8`) instead of the
retrieved UUID `chunk_id`, so citations could not be proven against evidence.

**Fix.** Evidence renders `Citation ID: <uuid>` and `Source label: <anchor>` separately; the prompt
enumerates the exact valid Citation IDs and requires citing those UUIDs only. The provenance gate in
[citation/service.py](../apps/api/app/modules/citation/service.py) rejects any id not in retrieved evidence.

**Verification.** Live `citation_validation` traces show `provenance: true` with real UUIDs for
successful answers; anchor-style and placeholder ids are rejected (see #8).

## 5. Clarification-prefixed text skipped citation validation — ✅ Resolved

**Problem.** Any output starting with `CLARIFY:` was treated as `clarification_required` before
parsing, so mixed text could bypass citation validation and hide citations from the UI.

**Fix.** The orchestrator in [answer/service.py](../apps/api/app/modules/answer/service.py) parses the
JSON draft first. Only a clean `clarification_required` draft (one question, no answer/citations)
bypasses citation validation; every substantive answer must pass the validation gates before storage.

**Verification.** Unit tests assert clarification drafts carrying answer text or citations are rejected;
substantive answers always run validation.

## 6. Prompt context duplicated the current question — ✅ Resolved

**Problem.** The current user message was stored before the prompt was built, so it appeared both in
the conversation-history block and in the explicit `Question:` field.

**Fix.** [conversation/service.py](../apps/api/app/modules/conversation/service.py) builds history from
prior turns only (`User:` / `Assistant (state):`, last ~4 round trips); the orchestrator fetches the
context *before* persisting the current message.

**Verification.** On the live stack, `conversation_context` for a two-turn conversation returns the
prior turns without duplicating the in-flight question.

## 7. UI rendering made mixed states confusing — ✅ Resolved

**Problem.** The frontend rendered the state badge alongside raw answer text that could contain
`PARTIAL:` sections, producing contradictory-looking output and hiding citations.

**Fix.** Backend never returns control markers now (#3). [AnswerCard.tsx](../apps/web/features/chat/AnswerCard.tsx)
renders clean `answer_text`, a single state badge, structured citation cards, and per-state copy
("Citations are hidden because validation failed", etc.).

**Verification.** Frontend tests cover answered, partial, clarification (no citations), and
`citation_validation_failed` rendering.

## 8. Weak model produced empty/parroted answers → `citation_validation_failed` — ✅ Resolved

**Problem.** Even with correct retrieval, the "What is Minh's favorite sport?" question kept returning
`citation_validation_failed`. The hobby chunk was retrieved #1, but `llama3.2:1b`, given the full
8-chunk evidence block, failed in escalating ways: it copied the schema placeholder
`retrieved-chunk-uuid`; then jammed all ids into one string; then parroted the prompt's one-shot
example answer (Adobe breaks), which the `claim_support` gate correctly rejected because it shared no
tokens with the badminton chunk. The validator was working; the model was overwhelmed by low-relevance
noise (7 Adobe chunks scoring ~0.1 alongside the relevant chunk at 2.0).

**Fix.** In [prompts.py](../apps/api/app/modules/answer/prompts.py):
- `select_prompt_chunks` shows the model only the top, high-relevance chunks (max 3, dropping any below
  30% of the top score); the full retrieved set is still used for provenance and the UI evidence panel.
- Cite exactly one Citation ID, chosen from an explicit bulleted list of valid ids.
- "At most two sentences" conciseness rule so long answers don't truncate the JSON past `max_tokens`.

**Verification.** Live, end-to-end through the API: 12/12 valid cited answers across three questions
(favorite sport, disliked sport, Adobe 2026 breaks). The sport question now returns `answered` with
"Minh's favorite sport is badminton…" cited to `Minh hobby#chunk-1`. Unit tests cover `select_prompt_chunks`.

## 9. `llama3.2:1b` comprehension limits on nuanced questions — ⚪ Accepted

**Problem.** The 1B model occasionally produces grounded-but-muddled answers (e.g., the "which sport
does Minh *dislike*" phrasing sometimes yields "badminton, which he dislikes…"). It is also
non-deterministic at `temperature: 0`, so the success rate on harder multi-chunk questions is not 100%.

**Status.** Accepted as a model-capacity limit, not a pipeline defect. The validation layer keeps wrong
answers from being surfaced (safe refusal instead). A stronger local model (the config already defaults
`ollama_model` to `llama3.1:8b`) would raise quality and consistency.

**Update (2026-06-18).** Challenge #11 forced the issue: generation is being moved off `llama3.2:1b`
to `llama3.1:8b` because 1b also cannot judge answerability. That switch supersedes the "keep 1b"
decision here and is expected to mitigate these comprehension limits as well.

## 10. Integration tests flake when a live LiteLLM is reachable — 🔴 Open

**Problem.** `apps/api/.env` sets `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=false` and points at
`localhost:4000`. With no LiteLLM running, deterministic-dependent integration tests pass (the gateway
falls back to the deterministic generator). With the Compose stack up, those same tests call the real,
flaky `llama3.2:1b` and can fail on `answered`-state assertions.

**Workaround.** Run the offline suite with the deterministic generator forced on:
`SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=true pytest tests/unit tests/integration` (59 passing).

**Proposed fix (not yet done).** Pin the deterministic-dependent integration tests to force
`local_deterministic_llm=True` via a fixture/marker, so they are independent of whatever LiteLLM is
reachable. The opt-in `test_e2e_live_answer.py` remains the only suite that exercises the live model.

## 11. Off-topic questions answered instead of refused — ✅ Resolved

**Problem.** A question the knowledge base does not cover returns a confident, wrongly-grounded answer
instead of refusing. "What is Minh's favorite food?" returned `answered` — "Minh's favorite sport is
badminton, which he enjoys playing for recreational purposes" — citing the sport chunk (which never
mentions food). All citation gates passed because the answer is grounded in the cited chunk; nothing
checks the chunk is relevant to the **question**.

**Root cause.** No question↔evidence relevance gate exists, and existing signals cannot supply one:
- The normalized merged retrieval score always pushes the top hit to ~2.0 even when it is only the
  best of a bad bunch ([ranking.py](../apps/api/app/modules/retrieval/ranking.py)), so `threshold_met` is meaningless for relevance.
- Raw vector cosine cannot separate the cases: food↔sport-chunk = 0.530, while a legitimate
  "How do I resolve SL-429?" = 0.503 and bare "SL-429" = 0.324 — sentence embeddings are dominated by
  the shared "Minh's favorite X" structure, so a cosine floor that refuses food also refuses valid
  lexical-match questions.
- `llama3.2:1b` cannot judge answerability: a strict "refuse if not addressed" instruction made it
  refuse the valid sport question too, and a separate yes/no relevance judge was degenerate (returned
  "NO" even for clearly answerable questions). Verified by probing embeddings and the model directly.

**Fix.** Added a relevance/answerability rule to `SYSTEM_INSTRUCTIONS` in
[prompts.py](../apps/api/app/modules/answer/prompts.py) ("refuse if the evidence does not state the specific information asked for") and
routed generation to `llama3.1:8b` via [infra/litellm.yaml](../infra/litellm.yaml), raising `llm_timeout_seconds` to 120s
so slow 8b inference does not time out into the deterministic fallback (which answers from `chunk[0]`
and would reproduce the bug). Deterministic score gating and lexical relevance gates were ruled out:
they break paraphrase retrieval and exact-match lookups respectively.

**Verification (passed).** Live on `llama3.1:8b`, deterministic across runs: "favorite food" and
"favorite color" → `refused_no_evidence` with no citations; "favorite sport", "what sport does Minh
dislike", and the Adobe 2026-break question → `answered` with one citation each. The refusal trace
shows `used_fallback: false` and `citation_validation.reason = "model_refused_no_evidence"` (the model
chose to refuse; retrieval still ran). Deterministic test suite: 59 passed. As a bonus this also fixed
the muddled "dislike" answer noted in #9 (now correctly "soccer, because it's prone to injury").

---

## Manual verification checklist

1. Rebuild images: `docker compose build api ingestion-worker evaluation-worker`
2. Start stack: `docker compose up -d`
3. Ensure the model is present: `docker compose exec ollama ollama pull llama3.2:1b`; confirm `curl -f http://localhost:4000/v1/models`.
4. Create + sync the source (admin headers `x-tenant-id`, `x-user-id`, `x-role: tenant_admin`):
   `POST /v1/admin/sources` then `POST /v1/admin/sources/{id}/sync`.
5. Confirm chunks report `embedding_model = sentence-transformers/all-MiniLM-L6-v2`
   (`SELECT embedding_model, count(*) FROM knowledge_chunks GROUP BY 1;`).
6. Ask the driving questions; confirm a single state, a cited answer (or one clarification), and
   **no** repeated `CLARIFY:`/`PARTIAL:` sub-responses.
7. Inspect the trace for retrieved chunk ids/anchors/scores, model stage, and `citation_validation`
   gate outcomes (`SELECT stage, metadata FROM answer_trace_stages WHERE trace_id = '<id>' ORDER BY id;`).

# SupportLens AI TODO

This list tracks pending work after the v1 scaffold. The current implementation is useful for local demos and tests, but several areas still need production-grade wiring.

## Persistence And Data Layer

- [x] Replace the default SQLite-style local database URL with PostgreSQL as the normal local/dev path.
- [x] Replace in-memory dictionaries in API service modules with real database persistence.
- [x] Add migrations and wire them into local setup.
- [ ] Wire migrations into CI.
- [x] Use the schema in `apps/api/app/db/schema.sql` as the starting point for managed migrations.
- [x] Add database session lifecycle management, transactions, and rollback behavior.
- [x] Persist conversations, messages, answers, citations, sources, chunks, audit events, traces, usage events, feedback, and evaluation results.

## Retrieval And Ingestion

- [x] Move retrieval from token-counter scoring to PostgreSQL full-text search, trigram search, and `pgvector`.
- [x] Generate and store real embeddings with `sentence-transformers`.
- [x] Add embedding version/model tracking and re-embedding workflow.
- [x] Convert ingestion job execution from immediate in-process calls to Redis/RQ workers.
- [x] Add retry, backoff, cleanup, permission refresh, scheduled refresh, and incremental update coverage in worker tests.
- [x] Expand source connectors beyond inline text and filesystem/markdown when the first real source is selected.
- [x] Validate last-known-good index behavior against PostgreSQL-backed data.
- [ ] Run `enqueue_scheduled_refreshes` on a periodic driver (RQ cron / `rq-scheduler` / external cron) so auto-sync sources refresh automatically; today it only runs when called explicitly.
- [ ] Add a scheduler service to `docker-compose.yml` (and a worker entrypoint) that triggers scheduled refresh on a configurable interval.

## LLM And Answer Quality

- [ ] Replace deterministic local answer generation with LiteLLM/Ollama calls.
- [ ] Add timeout, retry, and model-unavailable handling around LiteLLM.
- [ ] Strengthen prompt templates for grounded answers, refusals, clarifications, partial answers, and conflicting evidence.
- [ ] Expand citation validation beyond chunk-ID presence to claim support and citation span checks.
- [ ] Add tests for all answer states: answered, partial, clarification required, no evidence, unauthorized, source unavailable, model unavailable, and citation validation failed.
- [ ] Add a small launch evaluation dataset with representative support questions.

## Observability And Operations

- [ ] Add structured application logs with tenant-aware redaction.
- [ ] Ensure raw prompts, source text, retrieved snippets, and answers are logged only when tenant policy allows it.
- [ ] Persist audit events, answer traces, and usage events instead of storing them in memory.
- [ ] Add request IDs and trace IDs across API responses, logs, and worker jobs.
- [ ] Add operator-facing runbook notes for source sync failures, model failures, retrieval failures, and citation failures.
- [ ] Add basic health checks for Postgres, Redis, LiteLLM, Ollama, API, web, and workers.

## Security And Auth

- [ ] Replace header-only MVP auth with a production-ready auth boundary.
- [ ] Decide whether the next auth step is built-in username/password, Keycloak, OIDC, or SAML.
- [ ] Harden tenant and role enforcement on every protected route.
- [ ] Implement document-level ACL filtering when source systems provide permissions.
- [ ] Add access-denial audit events for sensitive paths.
- [ ] Add tests for unresolved permission metadata failing closed.
- [ ] Review retention and deletion behavior for conversations, traces, feedback, and evaluation artifacts.

## Frontend

- [ ] Connect the chat shell to live API calls.
- [ ] Connect admin source management screens to create, update, sync, and health APIs.
- [ ] Connect operator screens to trace, audit, usage, and health APIs.
- [ ] Add loading, empty, error, refusal, partial-answer, and citation-validation-failed states.
- [ ] Add citation inspection UI with access-safe failure behavior.
- [ ] Add feedback submission UI connected to the API.
- [ ] Add frontend tests for chat states, citation panel behavior, source health views, and operator trace views.

## Developer Experience And Documentation

- [ ] Switch API runtime/testing assumptions to ASGI-native patterns.
- [ ] Standardize test execution on `pytest`.
- [x] Add comments only where code is non-obvious, especially around policy, retrieval ranking, citation validation, and failure-state decisions.
- [ ] Expand the README with local setup, environment variables, Docker Compose usage, and troubleshooting.
- [ ] Add runbooks for local model setup, source ingestion, failed sync recovery, and launch evaluation.
- [ ] Add CI commands for API tests, API coverage, frontend lint/build, and Docker Compose config validation.
- [ ] Decide whether generated files such as `tsconfig.tsbuildinfo` should be ignored.
- [ ] Keep tests and coverage gates current as scaffolded services move to real persistence and infrastructure.

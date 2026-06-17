# SupportLens AI

SupportLens AI is a local-first, tenant-isolated support copilot that answers questions from approved knowledge sources with citations.

The current v1 scaffold includes:

- `apps/web`: Next.js app shell for chat, source admin, operator views, and feedback.
- `apps/api`: FastAPI backend for health, conversations, chat answers, source management, telemetry, and evaluation.
- `workers`: Python worker entrypoints for ingestion, evaluation, and scheduled refresh.
- `docker-compose.yml`: local stack for Postgres/pgvector, Redis, Ollama, LiteLLM, API, web, and workers.

The API uses deterministic local answer generation by default so tests and demos run without any LLM server. Setting `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=false` switches it to real generation through a local LiteLLM proxy backed by Ollama (this is what Docker Compose does). Retrieval is real hybrid search (PostgreSQL full-text + trigram + `pgvector`), and embeddings use `sentence-transformers` when the optional extra is installed, with a deterministic fallback otherwise.

## Prerequisites

- Python 3.9 or newer.
- Node.js and npm.
- Docker Desktop or another Docker Compose-compatible runtime.
- `curl` for quick health checks.

Optional but useful:

- A pulled Ollama model (for example `llama3.2:1b` or `llama3.1:8b`) to run real, non-deterministic answer generation.
- The `sentence-transformers` extra (`pip install -e '.[embeddings]'`) for real semantic embeddings instead of the deterministic fallback.
- `rg`/ripgrep for searching the repo.

## Run The Next.js App Locally

From the repo root:

```bash
cd apps/web
npm install
npm run dev
```

Open:

- `http://localhost:3000/` - landing page
- `http://localhost:3000/chat` - chat shell
- `http://localhost:3000/admin/sources` - source admin shell
- `http://localhost:3000/operator` - operator dashboard shell

Useful web commands:

```bash
cd apps/web
npm run lint
npm run build
```

## Run The API Locally

From the repo root:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'            # add ,embeddings for real embeddings: '.[test,embeddings]'
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Direct local API development uses the deterministic generator by default, so no LLM server is required. To call a real model locally, set `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=false` and point `SUPPORTLENS_LITELLM_BASE_URL` at a running LiteLLM proxy (see [Run With The Real LLM And Embeddings](#run-with-the-real-llm-and-embeddings)).

Settings are read from environment variables (prefix `SUPPORTLENS_`) or from an `apps/api/.env` file that is loaded automatically when you run from `apps/api`. The repo ships `apps/api/.env` listing every setting with its default (and `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=false` so the API uses the real model); `.env` is gitignored, so edit it freely for local overrides. Environment variables take precedence over the `.env` file.

In another terminal:

```bash
curl -f http://localhost:8000/health
```

The API expects simple MVP auth headers on protected routes:

```bash
curl -s http://localhost:8000/v1/conversations \
  -H 'x-tenant-id: demo-tenant' \
  -H 'x-user-id: demo-user' \
  -H 'x-role: end_user'
```

## Run The Full Local Stack

From the repo root:

```bash
docker compose up -d
```

The API container waits for Postgres and runs `alembic upgrade head` before starting Uvicorn. The Ollama and LiteLLM services are started and wired together, but by default the API still uses the deterministic generator (`SUPPORTLENS_LOCAL_DETERMINISTIC_LLM` defaults to `true`). To make the API call the real local model, add `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM: "false"` to the `api` service environment in `docker-compose.yml`.

Ollama starts with no models, so pull the one referenced by `infra/litellm.yaml` before asking real-model questions:

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

`llama3.1:8b` is higher quality but slow on CPU. For fast local runs, change `infra/litellm.yaml` to `model: ollama/llama3.2:1b` and pull that instead (`docker compose exec ollama ollama pull llama3.2:1b`).

Default local ports:

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- LiteLLM: `http://localhost:4000`
- Ollama: `http://localhost:11434`

Verify the API and the LiteLLM model mapping:

```bash
curl -f http://localhost:8000/health
curl -f http://localhost:4000/v1/models
```

Stop the stack:

```bash
docker compose down
```

### Run With The Real LLM And Embeddings

By default the stack runs deterministic generation. To run the full application end to end with a real model and real semantic embeddings, you have two options.

#### Option 1: Full stack in Docker Compose

1. Enable real generation for the API service. Add this line under the `api` service `environment:` in `docker-compose.yml`:

```yaml
      SUPPORTLENS_LOCAL_DETERMINISTIC_LLM: "false"
```

2. Start the stack and pull the model referenced by `infra/litellm.yaml`:

```bash
docker compose up -d
docker compose exec ollama ollama pull llama3.1:8b      # or llama3.2:1b for speed
```

3. Confirm the model is served, then add a source, sync it, and ask a question:

```bash
curl -f http://localhost:4000/v1/models                 # expects "supportlens-local"

# Add a URL source (admin role). Capture the created source id.
SOURCE=$(curl -s http://localhost:8000/v1/admin/sources \
  -H 'x-tenant-id: demo-tenant' -H 'x-user-id: demo-user' -H 'x-role: tenant_admin' \
  -H 'content-type: application/json' \
  -d '{"type":"url","name":"adobe-time-off","connection_ref":"https://benefits.adobe.com/us/time-off/vacation-and-paid-holidays"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# Sync it (creating a source does not auto-ingest). In Compose this runs on a worker.
curl -s -X POST http://localhost:8000/v1/admin/sources/$SOURCE/sync \
  -H 'x-tenant-id: demo-tenant' -H 'x-user-id: demo-user' -H 'x-role: tenant_admin' \
  -H 'content-type: application/json' -d '{"sync_reason":"manual_resync"}'

# Ask a question. The chat endpoint creates a conversation when none is given.
# The answer is generated by the real model, grounded in the synced evidence.
curl -s -X POST http://localhost:8000/v1/chat/messages \
  -H 'x-tenant-id: demo-tenant' -H 'x-user-id: demo-user' -H 'x-role: end_user' \
  -H 'content-type: application/json' \
  -d '{"message":"Does Adobe offer paid holidays and company break time off?"}'
```

With async ingestion (the Compose default), give the sync worker a moment to finish before asking, or check `GET /v1/admin/sources/$SOURCE/health`.

> Note: the Compose API image installs `pip install -e .` without the `embeddings` extra, so by default it uses the deterministic embedding fallback (retrieval still works, but embeddings are not semantically meaningful). For real `sentence-transformers` embeddings in Compose, change the API `Dockerfile` to `pip install --no-cache-dir -e '.[embeddings]'` (and the worker `Dockerfile` likewise) and rebuild, or use Option 2 below to run the API on the host with the extra installed.

#### Option 2: Run the API on the host against Compose model services

Useful for fast iteration with `--reload`. Run only the backing services in Docker and the API on your host:

```bash
# 1. Start datastores and the model proxy
docker compose up -d postgres redis ollama litellm
docker compose exec ollama ollama pull llama3.1:8b      # or llama3.2:1b for speed

# 2. Install the API with the embeddings extra and run it against those services.
#    apps/api/.env already sets LOCAL_DETERMINISTIC_LLM=false and localhost URLs.
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test,embeddings]'
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

To also exercise async ingestion on the host, set `SUPPORTLENS_INGESTION_ASYNC_ENABLED=true` in `apps/api/.env` and run a worker in another terminal. The worker imports both the `workers` package (repo root) and the `app` package (`apps/api`), so run it from the repo root with both on `PYTHONPATH`:

```bash
# from the repo root, reusing the API venv
source apps/api/.venv/bin/activate
PYTHONPATH="$PWD:$PWD/apps/api" python -m workers.ingestion.main
```

Note: the worker reads settings from environment variables, not the API's `apps/api/.env` (that file is only auto-loaded when the process runs from `apps/api`). Set `SUPPORTLENS_REDIS_URL` and `SUPPORTLENS_DATABASE_URL` in the worker's environment if they differ from the defaults.

## Run Tests And Checks

API tests live under `apps/api/tests`, split into `unit/` (isolated logic: citation parsing/validation, LiteLLM client, dataset loader) and `integration/` (API/DB/worker flows). The default run is fully offline: it mocks the LLM, and uses a real `pgvector` testcontainer when Docker is available, otherwise an in-memory SQLite fallback.

API tests:

```bash
cd apps/api
source .venv/bin/activate
pytest                      # whole suite
pytest tests/unit           # just unit tests
pytest tests/integration    # just integration tests
```

API coverage gate:

```bash
cd apps/api
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

### Live End-To-End Test (opt-in)

`tests/integration/test_e2e_live_answer.py` exercises the real path end to end: add a source (inline and a live `url` source), ingest + embed it with real `sentence-transformers`, start a conversation, ask a question, and have a real LLM (Ollama via LiteLLM) generate a grounded, cited answer. It auto-skips unless real Postgres, the `embeddings` extra, and a reachable LiteLLM proxy are all present, so the normal suite is unaffected.

To run it (Docker method):

```bash
# 1. From the repo root, start just Ollama + LiteLLM and pull a small, fast model.
docker compose up -d ollama litellm
docker compose exec ollama ollama pull llama3.2:1b   # match infra/litellm.yaml
curl -f http://localhost:4000/v1/models              # confirm "supportlens-local" is served

# 2. Run the test with the embeddings extra installed. SUPPORTLENS_E2E=1 makes a missing
#    service fail loudly instead of skipping.
cd apps/api
source .venv/bin/activate
pip install -e '.[test,embeddings]'
SUPPORTLENS_E2E=1 pytest tests/integration/test_e2e_live_answer.py -v
```

The test starts its own throwaway Postgres via testcontainers, so you do not need the Compose `postgres`/`api` services running. The first run downloads the embedding model and is slower; the live answer is non-deterministic, so the test asserts a valid safe answer state rather than fixed text. Tear down with `docker compose down` when finished.

Web checks:

```bash
cd apps/web
npm run lint
npm run build
npm audit --audit-level=moderate
```

Docker Compose config check:

```bash
docker compose config
```

## Configuration

The API reads settings from environment variables with the `SUPPORTLENS_` prefix. Common values:

| Variable | Default | Purpose |
|---|---|---|
| `SUPPORTLENS_DATABASE_URL` | `postgresql+psycopg://supportlens:supportlens@localhost:5432/supportlens` | API database URL. Docker Compose points this at the Postgres service. |
| `SUPPORTLENS_REDIS_URL` | `redis://localhost:6379/0` | Redis queue/cache URL. |
| `SUPPORTLENS_LITELLM_BASE_URL` | `http://localhost:4000/v1` | LiteLLM OpenAI-compatible endpoint the API calls for generation. |
| `SUPPORTLENS_LITELLM_MODEL` | `supportlens-local` | Logical model alias the API requests. The real model is whatever `infra/litellm.yaml` maps this alias to. |
| `SUPPORTLENS_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama runtime URL. Used by LiteLLM, not called directly by the API. |
| `SUPPORTLENS_OLLAMA_MODEL` | `llama3.1:8b` | Display-only metadata shown on `/health`. The actual model routing lives in `infra/litellm.yaml`, not here. |
| `SUPPORTLENS_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model used when the `embeddings` extra is installed; falls back to a deterministic embedder otherwise. |
| `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM` | `true` | When true, generation uses the deterministic local generator (no LLM server). Set `false` to call LiteLLM/Ollama. |
| `SUPPORTLENS_INGESTION_ASYNC_ENABLED` | `false` | When true, source sync runs on a Redis/RQ worker instead of inline in the request. Docker Compose sets this `true`. |

The web app reads:

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SUPPORTLENS_API_URL` | `http://localhost:8000` in Docker Compose | Browser-facing API URL. |

## Project Structure

```text
apps/
  api/
    app/main.py                    FastAPI entry point
    app/core/config.py             API settings
    app/db/                        SQLAlchemy models, sessions, migrations starter schema
    app/modules/auth_policy/       Tenant context, roles, fail-closed helpers
    app/modules/conversation/      Conversations, messages, feedback
    app/modules/answer/            Chat answer orchestration
    app/modules/retrieval/         MVP retrieval/ranking
    app/modules/source_management/ Source config, sync, source health
    app/modules/llm_gateway/        LiteLLM client, embeddings, model gateway
    app/modules/citation/           Citation parsing and validation
    app/modules/telemetry/         Audit, traces, usage
    app/modules/evaluation/        Evaluation, launch gate, launch dataset
    tests/unit/                    Isolated unit tests
    tests/integration/             API/DB/worker and live e2e tests
  web/
    app/                           Next.js routes
    features/                      Chat, admin, operator, feedback UI
workers/
  ingestion/                       Ingestion worker entrypoint and helpers
  evaluation/                      Evaluation worker entrypoint and jobs
  scheduler/                       Scheduled refresh enqueueing
docs/
  core_components/
    persistence_and_data_layer.md
    retrieval_and_ingestion.md
    llm_integration.md
  PRD.md
  HLD.md
  LLD.md
  TODO.md
```

## Current State And Limitations

Implemented:

- API data is persisted in PostgreSQL through SQLAlchemy with Alembic migrations.
- Retrieval is real hybrid search: PostgreSQL full-text + trigram + `pgvector`, with a portable in-Python fallback on SQLite for offline tests.
- Embeddings use `sentence-transformers` when the `embeddings` extra is installed, with a deterministic fallback otherwise.
- Answer generation can call a real local model via LiteLLM/Ollama (`SUPPORTLENS_LOCAL_DETERMINISTIC_LLM=false`); the deterministic generator remains the default for offline tests/demos.
- Ingestion can run inline or on Redis/RQ workers (`SUPPORTLENS_INGESTION_ASYNC_ENABLED=true`, as in Docker Compose), with scheduled refresh, retry, permission refresh, re-embedding, and cleanup jobs.

Still limited:

- The web UI is a shell and is not yet connected to live API calls.
- Auth is header-based MVP auth, not a production identity provider.
- Scheduled refresh is enqueued on demand; there is no always-on scheduler service yet.

See `docs/TODO.md` for the full pending hardening list.

## Troubleshooting

- If `npm run dev` fails, run `npm install` again in `apps/web`.
- If TypeScript or Next.js generated files look stale, remove `apps/web/.next` and rerun `npm run build`.
- If the API cannot import `app`, make sure you are running commands from `apps/api`.
- If protected API routes return `401`, include `x-tenant-id` and `x-user-id` headers.
- If protected API routes return `403`, check the `x-role` header.
- If Docker ports are already in use, stop the conflicting local service or change ports in `docker-compose.yml`.
- If the live e2e test is skipped, check the skip reason it prints: install `'.[embeddings]'`, ensure Docker is running (for the Postgres testcontainer), and confirm `curl http://localhost:4000/v1/models` returns `supportlens-local`.
- If live answers return `model_unavailable`, the model is not pulled: run `docker compose exec ollama ollama pull <model in infra/litellm.yaml>`.

## Where To Search

- App run commands: `README.md`, `apps/web/package.json`, `apps/api/pyproject.toml`
- Ports and services: `docker-compose.yml`
- API entry point: `apps/api/app/main.py`
- LLM model routing: `infra/litellm.yaml`
- Web routes: `apps/web/app`
- Tests: `apps/api/tests/unit`, `apps/api/tests/integration`
- Component deep dives: `docs/core_components/`
- Pending work: `docs/TODO.md`

Useful search:

```bash
rg "dev|localhost|NEXT_PUBLIC|SUPPORTLENS_|docker compose|health" README.md docker-compose.yml apps
```

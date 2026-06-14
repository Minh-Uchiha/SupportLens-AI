# SupportLens AI

SupportLens AI is a local-first, tenant-isolated support copilot that answers questions from approved knowledge sources with citations.

The current v1 scaffold includes:

- `apps/web`: Next.js app shell for chat, source admin, operator views, and feedback.
- `apps/api`: FastAPI backend for health, conversations, chat answers, source management, telemetry, and evaluation.
- `workers`: Python worker entrypoints for ingestion and evaluation.
- `docker-compose.yml`: local stack for Postgres/pgvector, Redis, Ollama, LiteLLM, API, web, and workers.

The API uses deterministic local answer generation by default so tests and demos can run without paid LLM access. LiteLLM/Ollama settings are present and can be wired to a live local model through configuration.

## Prerequisites

- Python 3.9 or newer.
- Node.js and npm.
- Docker Desktop or another Docker Compose-compatible runtime.
- `curl` for quick health checks.

Optional but useful:

- Ollama model pulled locally if you want to experiment with live local model calls later.
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
pip install -e '.[test]'
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

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

Default local ports:

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- LiteLLM: `http://localhost:4000`
- Ollama: `http://localhost:11434`

Verify the API:

```bash
curl -f http://localhost:8000/health
```

Stop the stack:

```bash
docker compose down
```

## Run Tests And Checks

API tests:

```bash
cd apps/api
source .venv/bin/activate
pytest
```

API coverage gate:

```bash
cd apps/api
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

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
| `SUPPORTLENS_DATABASE_URL` | `sqlite:///./supportlens.db` | API database URL. Docker Compose overrides this with Postgres. |
| `SUPPORTLENS_REDIS_URL` | `redis://localhost:6379/0` | Redis queue/cache URL. |
| `SUPPORTLENS_LITELLM_BASE_URL` | `http://localhost:4000/v1` | LiteLLM OpenAI-compatible endpoint. |
| `SUPPORTLENS_LITELLM_MODEL` | `supportlens-local` | Model name exposed through LiteLLM. |
| `SUPPORTLENS_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama runtime URL. |
| `SUPPORTLENS_OLLAMA_MODEL` | `llama3.1:8b` | Local Ollama model mapping. |
| `SUPPORTLENS_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Planned local embedding model. |
| `SUPPORTLENS_LOCAL_DETERMINISTIC_LLM` | `true` | Keeps demos/tests deterministic without live LLM calls. |

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
    app/modules/auth_policy/       Tenant context, roles, fail-closed helpers
    app/modules/conversation/      Conversations, messages, feedback
    app/modules/answer/            Chat answer orchestration
    app/modules/retrieval/         MVP retrieval/ranking
    app/modules/source_management/ Source config, sync, source health
    app/modules/telemetry/         Audit, traces, usage
    app/modules/evaluation/        Evaluation and launch gate APIs
  web/
    app/                           Next.js routes
    features/                      Chat, admin, operator, feedback UI
workers/
  ingestion/                       Ingestion worker entrypoint and helpers
  evaluation/                      Evaluation worker entrypoint and jobs
docs/
  PRD.md
  HLD.md
  LLD.md
  TODO.md
```

## Current MVP Limitations

- The service layer uses in-memory dictionaries for most data. `docker-compose.yml` includes Postgres, but persistence is not fully wired yet.
- Retrieval uses simple token overlap and token-counter cosine scoring, not PostgreSQL full-text/trigram/pgvector yet.
- Answer generation is deterministic local logic, not a live LiteLLM/Ollama model call yet.
- Worker entrypoints exist, but ingestion sync currently runs in-process through API service code.
- The web UI is a shell and is not fully connected to live API calls yet.

See `docs/TODO.md` for the pending hardening list.

## Troubleshooting

- If `npm run dev` fails, run `npm install` again in `apps/web`.
- If TypeScript or Next.js generated files look stale, remove `apps/web/.next` and rerun `npm run build`.
- If the API cannot import `app`, make sure you are running commands from `apps/api`.
- If protected API routes return `401`, include `x-tenant-id` and `x-user-id` headers.
- If protected API routes return `403`, check the `x-role` header.
- If Docker ports are already in use, stop the conflicting local service or change ports in `docker-compose.yml`.

## Where To Search

- App run commands: `README.md`, `apps/web/package.json`, `apps/api/pyproject.toml`
- Ports and services: `docker-compose.yml`
- API entry point: `apps/api/app/main.py`
- Web routes: `apps/web/app`
- Pending work: `docs/TODO.md`

Useful search:

```bash
rg "dev|localhost|NEXT_PUBLIC|SUPPORTLENS_|docker compose|health" README.md docker-compose.yml apps
```

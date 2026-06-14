# SupportLens AI

SupportLens AI is a local-first, tenant-isolated support copilot that answers questions from approved knowledge sources with citations.

## Quick Start

```bash
cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e '.[test]' && pytest
cd apps/web && npm install && npm run lint && npm run build
```

Docker Compose is provided for the v1 local stack:

```bash
docker compose up -d
curl -f http://localhost:8000/health
```

The API uses deterministic local answer generation by default so tests and demos can run without paid LLM access. LiteLLM/Ollama settings are present and can be wired to a live local model through configuration.

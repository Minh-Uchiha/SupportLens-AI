from __future__ import annotations

import logging

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.db.session import check_database, db_session_scope
from app.modules.answer.routes import router as answer_router
from app.modules.conversation.routes import router as conversation_router
from app.modules.evaluation.routes import router as evaluation_router
from app.modules.source_management.routes import router as source_router
from app.modules.telemetry.routes import router as telemetry_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    # Configure root logging once so module info/error logs (retrieval, ingestion, etc.)
    # surface. Uses force to take effect even if a library configured logging first.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
    app = FastAPI(title=resolved.app_name, version="0.1.0")
    app.state.settings = resolved

    @app.middleware("http")
    async def database_session_middleware(request, call_next):
        with db_session_scope(resolved):
            return await call_next(request)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": resolved.app_name,
            "environment": resolved.environment,
            "database_configured": check_database(resolved),
            "redis_configured": bool(resolved.redis_url),
            "litellm_configured": bool(resolved.litellm_base_url),
            "ollama_model": resolved.ollama_model,
            "embedding_model": resolved.embedding_model,
            "telemetry_enabled": resolved.telemetry_enabled,
        }

    app.include_router(conversation_router)
    app.include_router(answer_router)
    app.include_router(source_router)
    app.include_router(telemetry_router)
    app.include_router(evaluation_router)
    return app


app = create_app()

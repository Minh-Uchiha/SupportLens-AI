from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for local v1 services."""

    model_config = SettingsConfigDict(env_prefix="SUPPORTLENS_", env_file=".env", extra="ignore")

    app_name: str = "SupportLens AI"
    environment: str = "local"
    database_url: str = Field(default="postgresql+psycopg://supportlens:supportlens@localhost:5432/supportlens")
    redis_url: str = Field(default="redis://localhost:6379/0")
    litellm_base_url: str = Field(default="http://localhost:4000/v1")
    litellm_model: str = Field(default="supportlens-local")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:8b")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    telemetry_enabled: bool = True
    citation_required: bool = True
    max_retrieved_chunks: int = 8
    # When true, generation uses the deterministic offline generator instead of LiteLLM.
    # Defaults true so local dev and the offline test suite run without a live Ollama;
    # Docker Compose sets it false to exercise the real LiteLLM proxy path.
    local_deterministic_llm: bool = True
    # LiteLLM call budget. Transient failures (timeout, connection error, 5xx) are retried
    # up to llm_max_retries times with a fixed backoff, all within the timeout budget.
    # Generous timeout: the local model may be an 8B-class model on CPU, where a single
    # generation can take well over 30s. A short timeout would fall back to the deterministic
    # generator (which answers from the top chunk) and defeat the relevance refusal.
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 0.5
    llm_temperature: float = 0.0
    llm_max_tokens: int = 450
    # Conservative stop sequences sent to LiteLLM. These target the repeated-marker failure
    # pattern (llama3.2:1b emitting "CLARIFY: ... PARTIAL: ...") and runaway prose, NOT the JSON
    # itself: the draft is a single flat object, so "}" or a single "\n" could truncate valid
    # output. This is a secondary guard behind llm_max_tokens; an empty list disables it.
    llm_stop_sequences: list[str] = Field(default_factory=lambda: ["\nCLARIFY:", "\nPARTIAL:", "\n\n\n"])
    # When enabled, source sync runs on an RQ worker instead of inline in the request.
    # Defaults off so local dev and the synchronous test suite keep their current behavior;
    # Docker Compose turns it on.
    ingestion_async_enabled: bool = False
    # Retry budget and backoff (seconds) for transient ingestion failures on the worker.
    ingestion_max_retries: int = 3
    ingestion_retry_backoff_seconds: int = 5
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("llm_stop_sequences", mode="before")
    @classmethod
    def parse_stop_sequences(cls, value: object) -> object:
        # Allow a comma-separated env override; an empty/blank value disables stop sequences.
        if isinstance(value, str):
            return [item for item in value.split(",") if item]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

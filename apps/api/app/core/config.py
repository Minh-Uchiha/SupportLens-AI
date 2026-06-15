from __future__ import annotations

from functools import lru_cache
from pydantic import Field
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
    local_deterministic_llm: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

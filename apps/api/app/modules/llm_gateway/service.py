from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.llm_gateway.embeddings import (
    EMBEDDING_DIM,
    current_embedding_model,
    current_embedding_version,
    embed_texts,
)
from app.modules.llm_gateway.litellm_client import ModelCallError, complete
from app.modules.retrieval.schemas import EvidenceSet

logger = logging.getLogger(__name__)

__all__ = [
    "ModelResult",
    "PromptBundle",
    "call_model",
    "embed_texts",
    "EMBEDDING_DIM",
    "current_embedding_model",
    "current_embedding_version",
]

# Inline marker the model is asked to emit for each chunk it relies on, and that the
# orchestrator parses back out to learn which chunks were actually cited. Keeping the
# format explicit lets citation validation tie answer claims to retrieved evidence.
CITATION_PREFIX = "[[cite:"
CITATION_SUFFIX = "]]"


class ModelResult(BaseModel):
    text: str
    model: str = "deterministic-local"
    unavailable: bool = False
    # Populated for the trace so operators can see how generation behaved.
    latency_ms: float | None = None
    attempts: int = 1
    used_fallback: bool = False


class PromptBundle(BaseModel):
    question: str
    evidence: EvidenceSet
    instructions: str
    messages: list[dict[str, str]] = Field(default_factory=list)


def _deterministic_text(prompt_bundle: PromptBundle) -> str:
    """Produce a grounded answer from the leading evidence chunk, with a citation marker.

    This is intentionally not a real model: it extracts the first sentence of the top
    chunk and cites that chunk. It keeps the offline test suite and lightweight installs
    working and reproducible without a live Ollama.
    """
    leading = prompt_bundle.evidence.chunks[0]
    sentence = leading.text.strip().split(". ")[0].strip()
    answer = sentence if sentence.endswith(".") else f"{sentence}."
    return f"{answer} {CITATION_PREFIX}{leading.chunk_id}{CITATION_SUFFIX}"


def call_model(prompt_bundle: PromptBundle, model_options: dict | None = None) -> ModelResult:
    # Test hook: lets the model_unavailable path be exercised offline and deterministically.
    if "simulate_model_unavailable" in prompt_bundle.question.lower():
        return ModelResult(text="", unavailable=True)
    if not prompt_bundle.evidence.chunks:
        # No evidence: never ask the model to fill the gap. The orchestrator handles the
        # refusal; returning empty text keeps this path side-effect free.
        return ModelResult(text="", unavailable=False)

    settings = get_settings()
    if settings.local_deterministic_llm:
        return ModelResult(text=_deterministic_text(prompt_bundle), model="deterministic-local")

    started = time.perf_counter()
    attempts = settings.llm_max_retries + 1
    try:
        text = complete(prompt_bundle.messages)
        latency_ms = (time.perf_counter() - started) * 1000
        return ModelResult(text=text, model=settings.litellm_model, latency_ms=latency_ms, attempts=attempts)
    except ModelCallError:
        latency_ms = (time.perf_counter() - started) * 1000
        # Degrade to the deterministic generator so a proxy/runtime outage still yields a
        # grounded, cited answer instead of a hard failure. Only when that also cannot run
        # (no evidence, already handled above) do we report model_unavailable.
        logger.error("LiteLLM unavailable; using deterministic fallback latency_ms=%.1f", latency_ms)
        try:
            return ModelResult(
                text=_deterministic_text(prompt_bundle),
                model="deterministic-local",
                latency_ms=latency_ms,
                attempts=attempts,
                used_fallback=True,
            )
        except Exception:  # noqa: BLE001 - any fallback failure becomes model_unavailable
            logger.error("Deterministic fallback failed after LiteLLM outage", exc_info=True)
            return ModelResult(text="", model=settings.litellm_model, unavailable=True, attempts=attempts)

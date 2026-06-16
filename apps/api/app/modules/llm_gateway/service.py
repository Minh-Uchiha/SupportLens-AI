from __future__ import annotations

from pydantic import BaseModel

from app.modules.llm_gateway.embeddings import (
    EMBEDDING_DIM,
    current_embedding_model,
    current_embedding_version,
    embed_texts,
)
from app.modules.retrieval.schemas import EvidenceSet

__all__ = [
    "ModelResult",
    "PromptBundle",
    "call_model",
    "embed_texts",
    "EMBEDDING_DIM",
    "current_embedding_model",
    "current_embedding_version",
]


class ModelResult(BaseModel):
    text: str
    model: str = "deterministic-local"
    unavailable: bool = False


class PromptBundle(BaseModel):
    question: str
    evidence: EvidenceSet
    instructions: str


def call_model(prompt_bundle: PromptBundle, model_options: dict | None = None) -> ModelResult:
    if "simulate_model_unavailable" in prompt_bundle.question.lower():
        return ModelResult(text="", unavailable=True)
    if not prompt_bundle.evidence.chunks:
        return ModelResult(text="", unavailable=False)
    leading = prompt_bundle.evidence.chunks[0]
    sentence = leading.text.strip().split(". ")[0].strip()
    answer = sentence if sentence.endswith(".") else f"{sentence}."
    return ModelResult(text=answer)

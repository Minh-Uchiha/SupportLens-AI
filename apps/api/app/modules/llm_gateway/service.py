from __future__ import annotations

from pydantic import BaseModel

from app.modules.retrieval.schemas import EvidenceSet


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


def embed_texts(texts: list[str], embedding_options: dict | None = None) -> list[list[float]]:
    vectors = []
    for text in texts:
        tokens = text.lower().split()
        vectors.append([float(len(tokens)), float(len(set(tokens))), float(sum(len(token) for token in tokens))])
    return vectors

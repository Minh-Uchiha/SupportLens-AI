from __future__ import annotations

from app.modules.llm_gateway.service import PromptBundle
from app.modules.retrieval.schemas import EvidenceSet


def build_grounded_prompt(question: str, conversation_context: list[str], evidence: EvidenceSet) -> PromptBundle:
    instructions = (
        "Answer only from retrieved evidence. If evidence is missing, stale, conflicting, "
        "or uncited, refuse or ask for clarification."
    )
    if conversation_context:
        instructions += " Conversation history may clarify intent but must not be sole evidence."
    return PromptBundle(question=question, evidence=evidence, instructions=instructions)

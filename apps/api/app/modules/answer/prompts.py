from __future__ import annotations

from app.modules.llm_gateway.service import CITATION_PREFIX, CITATION_SUFFIX, PromptBundle
from app.modules.retrieval.schemas import EvidenceSet

# System policy the model must follow. It is explicit about every safe behavior the
# answer-state machine downstream can represent: grounded answers with citations,
# refusals, clarifications, partial answers, and conflicting-evidence handling.
SYSTEM_INSTRUCTIONS = (
    "You are SupportLens, an internal support assistant. Follow these rules strictly:\n"
    "- Answer ONLY using the supplied evidence. Never use outside knowledge.\n"
    f"- Cite every chunk you rely on inline using the exact marker {CITATION_PREFIX}<chunk_id>{CITATION_SUFFIX}.\n"
    "- If the evidence does not contain the answer, refuse and say you lack authorized evidence.\n"
    "- If the question is ambiguous, ask a single clarifying question and start it with 'CLARIFY:'.\n"
    "- If the evidence answers the question only partially, give what is supported, cite it, "
    "and begin the answer with 'PARTIAL:' to mark the gap.\n"
    "- If two pieces of evidence conflict, say so explicitly and cite both rather than choosing silently.\n"
    "- Conversation history may clarify intent but must never be the sole evidence source."
)


def _render_evidence(evidence: EvidenceSet) -> str:
    lines: list[str] = []
    for chunk in evidence.chunks:
        # Anchor each chunk with its id so the model can cite it and the orchestrator can
        # parse the citations back out for validation.
        lines.append(f"[{chunk.citation_anchor}] (chunk_id={chunk.chunk_id})\n{chunk.text}")
    return "\n\n".join(lines)


def build_grounded_prompt(question: str, conversation_context: list[str], evidence: EvidenceSet) -> PromptBundle:
    evidence_block = _render_evidence(evidence)
    history_block = "\n".join(conversation_context[-6:]) if conversation_context else "(none)"
    user_content = (
        f"Conversation so far:\n{history_block}\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        f"Question: {question}\n\n"
        f"Answer using only the evidence above and cite chunks with {CITATION_PREFIX}<chunk_id>{CITATION_SUFFIX}."
    )
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_content},
    ]
    instructions = SYSTEM_INSTRUCTIONS
    if conversation_context:
        instructions += " Conversation history may clarify intent but must not be sole evidence."
    return PromptBundle(question=question, evidence=evidence, instructions=instructions, messages=messages)

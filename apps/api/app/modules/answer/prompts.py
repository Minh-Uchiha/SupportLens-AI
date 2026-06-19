from __future__ import annotations

from app.modules.llm_gateway.service import PromptBundle
from app.modules.retrieval.schemas import EvidenceSet

# System policy the model must follow. It is explicit about every safe behavior the
# answer-state machine downstream can represent: grounded answers with citations,
# refusals, clarifications, partial answers, and conflicting-evidence handling.
SYSTEM_INSTRUCTIONS = (
    "You are SupportLens, an internal support assistant. Follow these rules strictly:\n"
    "- Answer ONLY using the supplied evidence. Never use outside knowledge.\n"
    "- Return exactly one JSON object and no other text.\n"
    "- JSON keys: state, answer, clarifying_question, citation_ids.\n"
    "- state must be one of: answered, partial, clarification_required, refused_no_evidence.\n"
    "- For answered or partial, put the user-facing answer in answer and cite only Citation ID values in citation_ids.\n"
    "- For clarification_required, ask exactly one question in clarifying_question and leave answer empty with no citations.\n"
    "- For refused_no_evidence, explain the lack of authorized evidence in answer and leave citation_ids empty.\n"
    "- Before answering, confirm the evidence actually states the specific information the question asks for. "
    "If it does not — the question is about a topic, attribute, or entity the evidence never addresses — "
    "set state to refused_no_evidence, briefly say the evidence does not cover it, and leave citation_ids empty. "
    "Never answer a different question than the one asked (e.g. do not answer about a sport when asked about food).\n"
    "- Never use CLARIFY:, PARTIAL:, markdown, bullet lists, or source labels as citations.\n"
    "- If two pieces of evidence conflict, say so explicitly and cite both rather than choosing silently.\n"
    "- Conversation history may clarify intent but must never be the sole evidence source.\n"
    "- Every citation_ids entry MUST be one of the supplied Citation ID values, wrapped in double quotes.\n"
    "- For answered or partial, answer MUST be a non-empty sentence; never return an empty answer with citations.\n"
    "- Keep answer to at most two sentences; summarize, never copy a long passage verbatim.\n"
    "\n"
    # Lightweight local models (e.g. llama3.2:1b) follow a concrete example far more reliably
    # than an abstract schema. This one-shot demonstrates correct quoting and a populated answer
    # using a placeholder id; the model must substitute real supplied Citation IDs.
    "Example of a valid response (copy the FORMAT only, never reuse this content or its id):\n"
    '{"state":"answered","answer":"Exempt employees who work at least 24 hours per week are paid '
    "their base salary during the 2026 company breaks (June 29-July 3 and December 24-31); "
    'non-exempt employees must use PTO.","clarifying_question":"","citation_ids":["00000000-0000-0000-0000-000000000000"]}'
)

OUTPUT_SCHEMA = (
    '{"state":"answered|partial|clarification_required|refused_no_evidence",'
    '"answer":"...",'
    '"clarifying_question":"...",'
    '"citation_ids":["retrieved-chunk-uuid"]}'
)


# How many retrieved chunks to actually show the model, and how far below the top score a
# chunk may fall before it is treated as noise. Retrieval returns a broad candidate set (good
# for traces, the UI evidence panel, and citation provenance), but a weak local model produces
# empty or parroted answers when the prompt is padded with low-relevance chunks. Showing only
# the top, clearly-relevant evidence keeps the model focused on what actually answers the question.
PROMPT_MAX_CHUNKS = 3
PROMPT_MIN_SCORE_FRACTION = 0.3


def select_prompt_chunks(evidence: EvidenceSet):
    """Pick the focused subset of evidence to put in the model prompt.

    Keeps the highest-scoring chunks, dropping those that score far below the top match, and
    always keeps at least the single best chunk so a relevant answer is never starved of context.
    """
    chunks = list(evidence.chunks)
    if not chunks:
        return chunks
    top_score = max((chunk.score for chunk in chunks), default=0.0)
    cutoff = top_score * PROMPT_MIN_SCORE_FRACTION if top_score > 0 else float("-inf")
    selected = [chunk for chunk in chunks if chunk.score >= cutoff]
    return (selected or chunks[:1])[:PROMPT_MAX_CHUNKS]


def _render_evidence(chunks) -> str:
    lines: list[str] = []
    for chunk in chunks:
        # Anchor each chunk with its id so the model can cite it and the orchestrator can
        # parse the citations back out for validation.
        lines.append(
            f"Citation ID: {chunk.chunk_id}\n"
            f"Source label: {chunk.citation_anchor}\n"
            f"Text: {chunk.text}"
        )
    return "\n\n".join(lines)


def build_grounded_prompt(question: str, conversation_context: list[str], evidence: EvidenceSet) -> PromptBundle:
    # Only show the model the focused, high-relevance evidence; the full retrieved set is still
    # used for citation provenance and the UI evidence panel downstream.
    prompt_chunks = select_prompt_chunks(evidence)
    evidence_block = _render_evidence(prompt_chunks)
    history_block = "\n".join(conversation_context[-6:]) if conversation_context else "(none)"
    # Enumerate the exact valid Citation IDs and make them the last, most salient instruction.
    # Weak local models (llama3.2:1b) anchor on the trailing tokens and copy whatever value the
    # schema shows for citation_ids: given the literal placeholder they copy "retrieved-chunk-uuid",
    # and given a comma-joined list they copy the whole list into one string. So present the ids
    # as a discrete bulleted set and require exactly ONE id as a single array element.
    valid_ids = "\n".join(f"- {chunk.chunk_id}" for chunk in prompt_chunks)
    user_content = (
        f"Conversation so far:\n{history_block}\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        f"Question: {question}\n\n"
        f"Return exactly this JSON shape (replace the citation_ids placeholder with a real id): {OUTPUT_SCHEMA}\n\n"
        f"citation_ids MUST contain exactly ONE value: the single Citation ID below whose Text "
        f"best answers the question, copied verbatim as one double-quoted array element. "
        f"Do NOT join multiple ids into one string and never output the word retrieved-chunk-uuid.\n"
        f"Valid Citation IDs:\n{valid_ids}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_content},
    ]
    instructions = SYSTEM_INSTRUCTIONS
    if conversation_context:
        instructions += " Conversation history may clarify intent but must not be sole evidence."
    return PromptBundle(question=question, evidence=evidence, instructions=instructions, messages=messages)

import type { AnswerResponse, Citation } from "../../lib/api";

const stateLabels: Record<AnswerResponse["answer_state"], string> = {
  answered: "Answered",
  partial: "Partial answer",
  clarification_required: "Clarification required",
  refused_no_evidence: "No evidence",
  refused_unauthorized: "Unauthorized",
  source_unavailable: "Source unavailable",
  model_unavailable: "Model unavailable",
  citation_validation_failed: "Citation validation failed",
};

const emptyCitationCopy: Record<AnswerResponse["answer_state"], string> = {
  answered: "No citations were returned for this answer.",
  partial: "No citations were returned for the partial answer.",
  clarification_required: "No citations are shown until the question can be answered.",
  refused_no_evidence: "No citations are available because no supporting evidence was found.",
  refused_unauthorized: "Citations are hidden because the request was not authorized.",
  source_unavailable: "Citations are unavailable while the source cannot be reached.",
  model_unavailable: "Citations are unavailable because the model did not complete the answer.",
  citation_validation_failed: "Citations are hidden because validation failed.",
};

type AnswerCardProps = {
  answer: AnswerResponse;
  selectedCitationId: string | null;
  onSelectCitation: (citation: Citation) => void;
};

export function AnswerCard({ answer, selectedCitationId, onSelectCitation }: AnswerCardProps) {
  const selectedCitation = answer.citations.find((citation) => citation.chunk_id === selectedCitationId) ?? answer.citations[0];

  return (
    <section className="answer-card" aria-live="polite">
      <div className="section-heading">
        <h2>Answer</h2>
        <span className={`badge state-${answer.answer_state}`}>{stateLabels[answer.answer_state]}</span>
      </div>
      <p className="answer-text">{answer.answer_text}</p>
      <dl className="meta-grid">
        <div>
          <dt>Conversation</dt>
          <dd>{answer.conversation_id}</dd>
        </div>
        <div>
          <dt>Trace</dt>
          <dd>{answer.trace_id}</dd>
        </div>
      </dl>

      <div className="citation-layout compact">
        <div>
          <h3>Citations</h3>
          {answer.citations.length > 0 ? (
            <ul className="citation-list" aria-label="Returned citations">
              {answer.citations.map((citation) => (
                <li key={citation.chunk_id}>
                  <button
                    className={citation.chunk_id === selectedCitation?.chunk_id ? "citation-button active" : "citation-button"}
                    type="button"
                    onClick={() => onSelectCitation(citation)}
                  >
                    {citation.citation_anchor}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{emptyCitationCopy[answer.answer_state]}</p>
          )}
        </div>

        <aside className="citation-panel" aria-label="Citation inspection">
          {selectedCitation ? (
            <>
              <h3>{selectedCitation.citation_anchor}</h3>
              <p>{selectedCitation.snippet}</p>
              <dl className="meta-grid">
                <div>
                  <dt>Source</dt>
                  <dd>{selectedCitation.source_id}</dd>
                </div>
                <div>
                  <dt>Document</dt>
                  <dd>{selectedCitation.document_id}</dd>
                </div>
                <div>
                  <dt>Chunk</dt>
                  <dd>{selectedCitation.chunk_id}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="muted">Citation details will appear after the API returns an access-safe citation.</p>
          )}
        </aside>
      </div>
    </section>
  );
}

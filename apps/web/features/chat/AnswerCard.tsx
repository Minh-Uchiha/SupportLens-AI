type Citation = {
  chunk_id: string;
  citation_anchor: string;
  snippet: string;
};

type AnswerCardProps = {
  answerState: string;
  answerText: string;
  citations: Citation[];
};

export function AnswerCard({ answerState, answerText, citations }: AnswerCardProps) {
  return (
    <section className="card">
      <span className="badge">{answerState}</span>
      <p>{answerText}</p>
      {citations.length > 0 ? (
        <ul>
          {citations.map((citation) => (
            <li key={citation.chunk_id}>
              <strong>{citation.citation_anchor}</strong>: {citation.snippet}
            </li>
          ))}
        </ul>
      ) : (
        <p>No citations returned for this classified answer state.</p>
      )}
    </section>
  );
}

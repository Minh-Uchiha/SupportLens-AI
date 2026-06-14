import { AnswerCard } from "./AnswerCard";

const demoAnswer = {
  answerState: "answered",
  answerText: "SupportLens AI returns concise answers only when retrieved evidence can support citations.",
  citations: [
    {
      chunk_id: "demo-chunk",
      citation_anchor: "SupportLens Demo#chunk-1",
      snippet: "Every substantive answer must cite source documents or source sections used.",
    },
  ],
};

export function ChatShell() {
  return (
    <div className="grid">
      <section className="card">
        <h1>SupportLens AI</h1>
        <p>Ask tenant-authorized support questions and inspect citations before trusting an answer.</p>
        <textarea aria-label="Support question" rows={5} defaultValue="How do I resolve SL-429?" />
        <p className="badge">Demo shell wired for API integration</p>
      </section>
      <AnswerCard {...demoAnswer} />
    </div>
  );
}

"use client";

import { FormEvent, useState } from "react";
import { submitFeedback, type Citation } from "../../lib/api";

const options = [
  { value: "helpful", label: "Helpful" },
  { value: "incorrect", label: "Incorrect" },
  { value: "missing_citation", label: "Missing citation" },
  { value: "bad_citation", label: "Bad citation" },
  { value: "missing_knowledge", label: "Missing knowledge" },
];

type FeedbackControlsProps = {
  answerId: string | null;
  citations: Citation[];
  selectedCitationId: string | null;
};

export function FeedbackControls({ answerId, citations, selectedCitationId }: FeedbackControlsProps) {
  const [feedbackType, setFeedbackType] = useState(options[0].value);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "submitted" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const citationId = selectedCitationId ?? citations[0]?.chunk_id ?? null;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answerId) {
      return;
    }
    setStatus("submitting");
    setError(null);
    try {
      await submitFeedback({
        answer_id: answerId,
        citation_id: citationId,
        feedback_type: feedbackType,
        comment: comment.trim() || null,
      });
      setStatus("submitted");
      setComment("");
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Feedback could not be submitted.");
    }
  }

  return (
    <section className="feedback-panel">
      <div className="section-heading">
        <h2>Feedback</h2>
        {citationId ? <span className="badge">citation selected</span> : <span className="badge neutral">answer only</span>}
      </div>
      <form className="stack" onSubmit={onSubmit}>
        <fieldset className="segmented-control" disabled={!answerId || status === "submitting"}>
          <legend>Feedback type</legend>
          {options.map((option) => (
            <label key={option.value}>
              <input
                checked={feedbackType === option.value}
                name="feedback-type"
                onChange={() => setFeedbackType(option.value)}
                type="radio"
                value={option.value}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>
        <label className="field">
          <span>Comment</span>
          <textarea
            aria-label="Feedback comment"
            disabled={!answerId || status === "submitting"}
            onChange={(event) => setComment(event.target.value)}
            rows={3}
            value={comment}
          />
        </label>
        <button disabled={!answerId || status === "submitting"} type="submit">
          {status === "submitting" ? "Submitting..." : "Submit feedback"}
        </button>
      </form>
      {!answerId ? <p className="muted">Feedback unlocks after an answer returns from the API.</p> : null}
      {status === "submitted" ? <p className="success">Feedback submitted.</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

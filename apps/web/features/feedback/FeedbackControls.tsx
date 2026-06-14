const options = ["helpful", "incorrect", "missing_citation", "bad_citation", "missing_knowledge"];

export function FeedbackControls() {
  return (
    <section className="card">
      <h2>Feedback</h2>
      <p>Capture quality signals for answer usefulness, citation quality, and missing knowledge.</p>
      {options.map((option) => (
        <button key={option} type="button">{option}</button>
      ))}
    </section>
  );
}

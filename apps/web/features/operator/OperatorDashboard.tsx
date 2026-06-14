export function OperatorDashboard() {
  return (
    <section className="card">
      <h2>Operator Dashboard</h2>
      <p>Trace answer stages across policy, retrieval, model call, citation validation, and final answer state.</p>
      <div className="grid">
        <span className="badge">refusal rate</span>
        <span className="badge">source health</span>
        <span className="badge">model errors</span>
        <span className="badge">ingestion backlog</span>
      </div>
    </section>
  );
}

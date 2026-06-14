export function SourceAdmin() {
  return (
    <section className="card">
      <h2>Source Management</h2>
      <p>Register approved documentation sources, trigger sync, and review freshness or failure status.</p>
      <ul>
        <li>Initial sync</li>
        <li>Manual resync</li>
        <li>Retry failed sync</li>
        <li>Permission refresh</li>
      </ul>
    </section>
  );
}

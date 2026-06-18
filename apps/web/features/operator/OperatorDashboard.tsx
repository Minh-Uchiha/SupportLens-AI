"use client";

import { FormEvent, useEffect, useState } from "react";
import { Activity, FileClock, Gauge, RefreshCw, Search, ShieldCheck } from "lucide-react";
import {
  getOperatorHealth,
  getOperatorUsage,
  getTrace,
  listAuditEvents,
  type AnswerTrace,
  type AuditEvent,
  type OperatorHealth,
} from "../../lib/api";

export function OperatorDashboard() {
  const [health, setHealth] = useState<OperatorHealth | null>(null);
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [traceId, setTraceId] = useState("");
  const [trace, setTrace] = useState<AnswerTrace | null>(null);
  const [status, setStatus] = useState<"loading" | "idle" | "error">("loading");
  const [traceStatus, setTraceStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);

  async function refresh() {
    setStatus("loading");
    setError(null);
    try {
      const [healthResponse, usageResponse, auditResponse] = await Promise.all([
        getOperatorHealth(),
        getOperatorUsage(),
        listAuditEvents(),
      ]);
      setHealth(healthResponse);
      setUsage(usageResponse);
      setAuditEvents(auditResponse);
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Could not load operator data.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onTraceLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = traceId.trim();
    if (!trimmed) {
      return;
    }
    setTraceStatus("loading");
    setTraceError(null);
    setTrace(null);
    try {
      setTrace(await getTrace(trimmed));
      setTraceStatus("idle");
    } catch (caught) {
      setTraceStatus("error");
      setTraceError(caught instanceof Error ? caught.message : "Trace could not be loaded.");
    }
  }

  const usageTotal = Object.values(usage).reduce((total, value) => total + value, 0);

  return (
    <main className="operator-page">
      <section className="page-hero operator-hero">
        <div>
          <span className="eyebrow">Operations view</span>
          <h1>Operator Dashboard</h1>
          <p>Monitor answer flow, trace stages, audit events, and usage signals across the tenant.</p>
        </div>
        <button className="secondary-button" disabled={status === "loading"} onClick={() => void refresh()} type="button">
          <RefreshCw size={18} />
          Refresh
        </button>
      </section>

      {error ? <p className="error banner" role="alert">{error}</p> : null}
      {status === "loading" ? <p className="muted" role="status">Loading operator data...</p> : null}

      <section className="metric-grid">
        <article className="metric-card">
          <Gauge size={22} />
          <span>Status</span>
          <strong>{health?.status ?? "unknown"}</strong>
        </article>
        <article className="metric-card">
          <Activity size={22} />
          <span>Traces</span>
          <strong>{health?.trace_count ?? 0}</strong>
        </article>
        <article className="metric-card">
          <ShieldCheck size={22} />
          <span>Audit events</span>
          <strong>{health?.audit_count ?? 0}</strong>
        </article>
        <article className="metric-card">
          <FileClock size={22} />
          <span>Usage total</span>
          <strong>{usageTotal}</strong>
        </article>
      </section>

      <div className="operator-grid">
        <section className="panel">
          <h2>Usage breakdown</h2>
          {Object.keys(usage).length === 0 ? (
            <div className="empty-state compact-empty">
              <Activity size={28} />
              <p>No usage events yet. Ask a question in Chat to populate this panel.</p>
            </div>
          ) : (
            <div className="usage-list">
              {Object.entries(usage).map(([eventType, quantity]) => (
                <div className="usage-row" key={eventType}>
                  <span>{eventType}</span>
                  <strong>{quantity}</strong>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="section-heading">
            <h2>Recent audit activity</h2>
            <span className="badge neutral">{auditEvents.length} events</span>
          </div>
          {auditEvents.length === 0 ? (
            <div className="empty-state compact-empty">
              <ShieldCheck size={28} />
              <p>No audit activity yet. Source changes and sync actions will appear here.</p>
            </div>
          ) : (
            <ul className="activity-list">
              {auditEvents.slice(-8).reverse().map((event) => (
                <li key={event.id}>
                  <strong>{event.action}</strong>
                  <span>{event.resource_type}</span>
                  <small>{event.actor_id}</small>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel trace-lookup-panel">
          <h2>Trace lookup</h2>
          <form className="inline-form" onSubmit={onTraceLookup}>
            <label className="field">
              <span>Trace ID</span>
              <input onChange={(event) => setTraceId(event.target.value)} placeholder="Paste trace id from a chat answer" value={traceId} />
            </label>
            <button disabled={traceStatus === "loading" || !traceId.trim()} type="submit">
              <Search size={18} />
              {traceStatus === "loading" ? "Loading..." : "Load trace"}
            </button>
          </form>
          {traceError ? <p className="error" role="alert">{traceError}</p> : null}
        </section>

        <section className="panel trace-panel-wide">
          <div className="section-heading">
            <h2>Trace stages</h2>
            {trace ? <span className="badge">{trace.answer_state}</span> : <span className="badge neutral">no trace loaded</span>}
          </div>
          {trace ? (
            <>
              <dl className="meta-grid">
                <div>
                  <dt>Trace</dt>
                  <dd>{trace.id}</dd>
                </div>
                <div>
                  <dt>Conversation</dt>
                  <dd>{trace.conversation_id ?? "none"}</dd>
                </div>
                <div>
                  <dt>Redaction</dt>
                  <dd>{trace.redaction_status}</dd>
                </div>
              </dl>
              {trace.stages.length === 0 ? (
                <p className="muted">No trace stages returned.</p>
              ) : (
                <ol className="timeline">
                  {trace.stages.map((stage) => (
                    <li key={`${stage.stage}-${stage.created_at}`}>
                      <span className="timeline-dot" />
                      <div>
                        <strong>{stage.stage}</strong>
                        <code>{JSON.stringify(stage.metadata)}</code>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <div className="empty-state compact-empty">
              <Search size={28} />
              <p>Paste a trace ID from a chat answer to inspect policy, retrieval, model, and citation stages.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

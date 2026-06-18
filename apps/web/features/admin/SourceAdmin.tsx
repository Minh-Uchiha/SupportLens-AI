"use client";

import { FormEvent, useEffect, useState } from "react";
import { DatabaseZap, Play, RefreshCw, RotateCcw, Save, ShieldCheck, Sparkles, ToggleLeft } from "lucide-react";
import {
  createSource,
  getSourceHealth,
  listSourceJobs,
  listSources,
  reembedSource,
  triggerSourceSync,
  updateSource,
  type IngestionJob,
  type KnowledgeSource,
  type SourceCreatePayload,
  type SourceHealth,
} from "../../lib/api";

type SourceType = "inline" | "url" | "filesystem" | "markdown";

type DraftSource = SourceCreatePayload & {
  status: string;
};

const emptyDraft: DraftSource = {
  type: "inline",
  name: "",
  connection_ref: "",
  sync_policy: "manual",
  permission_mode: "tenant",
  status: "enabled",
};

const sourceTypes: Array<{ value: SourceType; label: string; helper: string }> = [
  { value: "inline", label: "Inline text", helper: "Paste a runbook, FAQ, or policy excerpt." },
  { value: "url", label: "URL", helper: "Fetch and index a public documentation page." },
  { value: "filesystem", label: "Filesystem", helper: "Index a markdown file or directory path." },
  { value: "markdown", label: "Markdown", helper: "Read markdown from a local path." },
];

export function SourceAdmin() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [healthBySource, setHealthBySource] = useState<Record<string, SourceHealth>>({});
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [draft, setDraft] = useState<DraftSource>(emptyDraft);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "idle" | "saving" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const selectedSource = sources.find((source) => source.id === selectedSourceId) ?? null;
  const isEditing = Boolean(selectedSource);

  async function refresh(keepStatus = false) {
    if (!keepStatus) {
      setStatus((current) => (current === "saving" ? current : "loading"));
    }
    setError(null);
    try {
      const [sourceRows, jobRows] = await Promise.all([listSources(), listSourceJobs()]);
      const healthPairs = await Promise.all(
        sourceRows.map(async (source) => [source.id, await getSourceHealth(source.id)] as const),
      );
      setSources(sourceRows);
      setJobs(jobRows);
      setHealthBySource(Object.fromEntries(healthPairs));
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Could not load source management data.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  function startNewSource() {
    setSelectedSourceId(null);
    setDraft(emptyDraft);
    setError(null);
  }

  function selectSource(source: KnowledgeSource) {
    setSelectedSourceId(source.id);
    setDraft({
      type: source.type,
      name: source.name,
      connection_ref: source.connection_ref,
      sync_policy: source.sync_policy,
      permission_mode: source.permission_mode,
      status: source.status,
    });
    setError(null);
  }

  function updateDraft(field: keyof DraftSource, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function saveSource(syncAfterCreate: boolean) {
    if (!draft.name.trim()) {
      setError("Source name is required.");
      return;
    }

    setStatus("saving");
    setError(null);
    try {
      if (selectedSource) {
        await updateSource(selectedSource.id, {
          type: draft.type,
          name: draft.name.trim(),
          connection_ref: draft.connection_ref.trim(),
          sync_policy: draft.sync_policy,
          permission_mode: draft.permission_mode,
          status: draft.status,
        });
      } else {
        const created = await createSource({
          type: draft.type,
          name: draft.name.trim(),
          connection_ref: draft.connection_ref.trim(),
          sync_policy: draft.sync_policy,
          permission_mode: draft.permission_mode,
        });
        setSelectedSourceId(created.id);
        if (syncAfterCreate) {
          await triggerSourceSync(created.id, "initial_sync");
        }
      }
      await refresh(true);
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Source action failed.");
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await saveSource(false);
  }

  async function runSourceAction(sourceId: string, action: () => Promise<unknown>) {
    setStatus("saving");
    setError(null);
    try {
      await action();
      await refresh(true);
      setSelectedSourceId(sourceId);
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Source action failed.");
    }
  }

  const inputLabel =
    draft.type === "inline"
      ? "Inline source text"
      : draft.type === "url"
        ? "Documentation URL"
        : "Filesystem path";

  return (
    <main className="source-page">
      <section className="page-hero source-hero">
        <div>
          <span className="eyebrow">Knowledge operations</span>
          <h1>Source Management</h1>
          <p>Create knowledge sources, sync them into retrieval, and watch health in one place.</p>
        </div>
        <button className="secondary-button" disabled={status === "loading" || status === "saving"} onClick={() => void refresh()} type="button">
          <RefreshCw size={18} />
          Refresh
        </button>
      </section>

      {error ? <p className="error banner" role="alert">{error}</p> : null}

      <div className="source-console">
        <section className="panel source-form-panel">
          <div className="section-heading">
            <div>
              <h2>{isEditing ? "Edit source" : "New source"}</h2>
              <p className="muted">{isEditing ? "Update configuration or run a fresh sync." : "Add approved knowledge and make it searchable."}</p>
            </div>
            <button className="secondary-button" onClick={startNewSource} type="button">
              <DatabaseZap size={18} />
              New source
            </button>
          </div>

          <form className="source-form" onSubmit={onSubmit}>
            <label className="field">
              <span>Source type</span>
              <select value={draft.type} onChange={(event) => updateDraft("type", event.target.value)}>
                {sourceTypes.map((sourceType) => (
                  <option key={sourceType.value} value={sourceType.value}>
                    {sourceType.label}
                  </option>
                ))}
              </select>
              <small>{sourceTypes.find((sourceType) => sourceType.value === draft.type)?.helper}</small>
            </label>

            <label className="field">
              <span>Source name</span>
              <input onChange={(event) => updateDraft("name", event.target.value)} placeholder="Rate limit runbook" value={draft.name} />
            </label>

            <label className="field span-full">
              <span>{inputLabel}</span>
              {draft.type === "inline" ? (
                <textarea
                  onChange={(event) => updateDraft("connection_ref", event.target.value)}
                  placeholder="Paste support content, docs, or runbook text..."
                  rows={8}
                  value={draft.connection_ref}
                />
              ) : (
                <input
                  onChange={(event) => updateDraft("connection_ref", event.target.value)}
                  placeholder={draft.type === "url" ? "https://docs.example.com/article" : "/path/to/docs"}
                  type={draft.type === "url" ? "url" : "text"}
                  value={draft.connection_ref}
                />
              )}
            </label>

            <label className="field">
              <span>Sync policy</span>
              <select value={draft.sync_policy} onChange={(event) => updateDraft("sync_policy", event.target.value)}>
                <option value="manual">Manual</option>
                <option value="scheduled">Scheduled</option>
                <option value="incremental">Incremental</option>
              </select>
            </label>

            <label className="field">
              <span>Permission mode</span>
              <select value={draft.permission_mode} onChange={(event) => updateDraft("permission_mode", event.target.value)}>
                <option value="tenant">Tenant</option>
                <option value="source_acl">Source ACL</option>
                <option value="restricted">Restricted</option>
              </select>
            </label>

            <label className="field">
              <span>Status</span>
              <select value={draft.status} onChange={(event) => updateDraft("status", event.target.value)}>
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
              </select>
            </label>

            <div className="form-actions span-full">
              <button disabled={status === "saving" || !draft.name.trim()} type="submit">
                <Save size={18} />
                {isEditing ? "Save changes" : "Create source"}
              </button>
              {!isEditing ? (
                <button
                  className="accent-button"
                  disabled={status === "saving" || !draft.name.trim()}
                  onClick={() => void saveSource(true)}
                  type="button"
                >
                  <Play size={18} />
                  Create and sync
                </button>
              ) : null}
            </div>
          </form>
        </section>

        <section className="panel source-list-panel">
          <div className="section-heading">
            <h2>Configured sources</h2>
            <span className="badge neutral">{sources.length} total</span>
          </div>

          {status === "loading" ? <p className="muted" role="status">Loading sources...</p> : null}
          {sources.length === 0 && status !== "loading" ? (
            <div className="empty-state">
              <DatabaseZap size={34} />
              <h3>No sources yet</h3>
              <p>Create an inline runbook or URL source, then sync it so chat can retrieve citations.</p>
            </div>
          ) : (
            <div className="source-list">
              {sources.map((source) => {
                const health = healthBySource[source.id];
                const isSelected = source.id === selectedSourceId;
                return (
                  <article className={isSelected ? "source-card selected" : "source-card"} key={source.id}>
                    <button className="source-card-main" onClick={() => selectSource(source)} type="button">
                      <span>
                        <strong>{source.name}</strong>
                        <small>{source.type} source</small>
                      </span>
                      <span className="badge">{source.status}</span>
                    </button>
                    <dl className="source-health-grid">
                      <div>
                        <dt>Sync</dt>
                        <dd>{source.last_sync_status}</dd>
                      </div>
                      <div>
                        <dt>Freshness</dt>
                        <dd>{health?.freshness ?? "unknown"}</dd>
                      </div>
                      <div>
                        <dt>Docs</dt>
                        <dd>{health?.document_count ?? 0}</dd>
                      </div>
                      <div>
                        <dt>Chunks</dt>
                        <dd>{health?.chunk_count ?? 0}</dd>
                      </div>
                    </dl>
                    {health?.failure_reason ? <p className="error">{health.failure_reason}</p> : null}
                    <div className="source-actions">
                      <button onClick={() => void runSourceAction(source.id, () => triggerSourceSync(source.id, "manual_resync"))} type="button">
                        <Play size={16} />
                        Sync now
                      </button>
                      <button onClick={() => void runSourceAction(source.id, () => triggerSourceSync(source.id, "retry_failed_sync"))} type="button">
                        <RotateCcw size={16} />
                        Retry sync
                      </button>
                      <button onClick={() => void runSourceAction(source.id, () => triggerSourceSync(source.id, "permission_refresh"))} type="button">
                        <ShieldCheck size={16} />
                        Permission refresh
                      </button>
                      <button onClick={() => void runSourceAction(source.id, () => reembedSource(source.id))} type="button">
                        <Sparkles size={16} />
                        Re-embed
                      </button>
                      <button
                        onClick={() =>
                          void runSourceAction(source.id, () =>
                            updateSource(source.id, { status: source.status === "enabled" ? "disabled" : "enabled" }),
                          )
                        }
                        type="button"
                      >
                        <ToggleLeft size={16} />
                        {source.status === "enabled" ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="section-heading">
          <h2>Ingestion jobs</h2>
          <span className="badge neutral">{jobs.length} total</span>
        </div>
        {jobs.length === 0 ? (
          <p className="muted">Sync, retry, permission refresh, and re-embed jobs will appear here.</p>
        ) : (
          <div className="job-grid">
            {jobs.map((job) => (
              <article className="job-card" key={job.id}>
                <strong>{job.job_type.replaceAll("_", " ")}</strong>
                <span className="badge">{job.status}</span>
                <small>{job.source_id}</small>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

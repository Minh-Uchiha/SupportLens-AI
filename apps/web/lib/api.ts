export const apiBaseUrl = process.env.NEXT_PUBLIC_SUPPORTLENS_API_URL ?? "http://localhost:8000";

export const demoHeaders = {
  "content-type": "application/json",
  "x-tenant-id": "demo-tenant",
  "x-user-id": "demo-user",
  "x-role": "tenant_admin,platform_operator,end_user",
};

export type AnswerState =
  | "answered"
  | "partial"
  | "clarification_required"
  | "refused_no_evidence"
  | "refused_unauthorized"
  | "source_unavailable"
  | "model_unavailable"
  | "citation_validation_failed";

export type Citation = {
  chunk_id: string;
  source_id: string;
  document_id: string;
  citation_anchor: string;
  snippet: string;
};

export type AnswerResponse = {
  answer_id: string;
  conversation_id: string;
  answer_state: AnswerState;
  answer_text: string;
  citations: Citation[];
  evidence: unknown[];
  trace_id: string;
};

export type KnowledgeSource = {
  id: string;
  tenant_id: string;
  type: string;
  name: string;
  connection_ref: string;
  status: string;
  sync_policy: string;
  permission_mode: string;
  last_sync_at: string | null;
  last_sync_status: string;
  last_failure_reason: string | null;
};

export type SourceHealth = {
  source_id: string;
  status: string;
  last_sync: string | null;
  last_sync_status: string;
  failure_reason: string | null;
  document_count: number;
  chunk_count: number;
  freshness: string;
};

export type IngestionJob = {
  id: string;
  tenant_id: string;
  source_id: string;
  job_type: string;
  status: string;
  reason: string | null;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  tenant_id: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  created_at: string;
};

export type OperatorHealth = {
  tenant_id: string;
  trace_count: number;
  audit_count: number;
  usage: Record<string, number>;
  status: string;
};

export type AnswerTrace = {
  id: string;
  tenant_id: string;
  conversation_id: string | null;
  stages: Array<{ stage: string; metadata: Record<string, unknown>; created_at: string }>;
  answer_state: string;
  redaction_status: string;
  created_at: string;
};

export type SourceCreatePayload = {
  type: string;
  name: string;
  connection_ref: string;
  sync_policy: string;
  permission_mode: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      ...demoHeaders,
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the backend sends an empty or non-JSON error.
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function postChatMessage(payload: { conversation_id?: string; message: string; source_filters?: string[] }) {
  return request<AnswerResponse>("/v1/chat/messages", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitFeedback(payload: {
  answer_id: string;
  citation_id?: string | null;
  feedback_type: string;
  comment?: string | null;
}) {
  return request<{ id: string }>("/v1/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listSources() {
  return request<KnowledgeSource[]>("/v1/admin/sources");
}

export function createSource(payload: SourceCreatePayload) {
  return request<KnowledgeSource>("/v1/admin/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSource(sourceId: string, payload: Partial<SourceCreatePayload & { status: string }>) {
  return request<KnowledgeSource>(`/v1/admin/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function triggerSourceSync(sourceId: string, syncReason: string) {
  return request<IngestionJob>(`/v1/admin/sources/${sourceId}/sync`, {
    method: "POST",
    body: JSON.stringify({ sync_reason: syncReason }),
  });
}

export function reembedSource(sourceId: string) {
  return request<IngestionJob>(`/v1/admin/sources/${sourceId}/reembed`, {
    method: "POST",
  });
}

export function getSourceHealth(sourceId: string) {
  return request<SourceHealth>(`/v1/admin/sources/${sourceId}/health`);
}

export function listSourceJobs() {
  return request<IngestionJob[]>("/v1/admin/sources/jobs/list");
}

export function getOperatorHealth() {
  return request<OperatorHealth>("/v1/operator/health");
}

export function getOperatorUsage() {
  return request<Record<string, number>>("/v1/operator/usage");
}

export function listAuditEvents() {
  return request<AuditEvent[]>("/v1/operator/audit");
}

export function getTrace(traceId: string) {
  return request<AnswerTrace>(`/v1/operator/traces/${traceId}`);
}

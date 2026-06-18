import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OperatorDashboard } from "./OperatorDashboard";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? "OK" : "Not found",
    json: async () => body,
  } as Response);
}

beforeEach(() => {
  global.fetch = jest.fn((input: RequestInfo | URL) => {
    const url = input.toString();
    if (url.endsWith("/v1/operator/health")) {
      return jsonResponse({ tenant_id: "demo-tenant", trace_count: 2, audit_count: 1, usage: { answer: 3 }, status: "ok" });
    }
    if (url.endsWith("/v1/operator/usage")) {
      return jsonResponse({ answer: 3, tokens: 25 });
    }
    if (url.endsWith("/v1/operator/audit")) {
      return jsonResponse([
        {
          id: "audit-1",
          tenant_id: "demo-tenant",
          actor_id: "admin",
          action: "source.create",
          resource_type: "knowledge_source",
          resource_id: "source-1",
          created_at: "2026-01-01T00:00:00",
        },
      ]);
    }
    if (url.endsWith("/v1/operator/traces/trace-1")) {
      return jsonResponse({
        id: "trace-1",
        tenant_id: "demo-tenant",
        conversation_id: "conversation-1",
        stages: [{ stage: "retrieval", metadata: { chunks: 2 }, created_at: "2026-01-01T00:00:00" }],
        answer_state: "answered",
        redaction_status: "redacted",
        created_at: "2026-01-01T00:00:00",
      });
    }
    return jsonResponse({ detail: "Trace not found" }, 404);
  });
});

afterEach(() => {
  jest.resetAllMocks();
});

test("renders operator health, usage, and audit data", async () => {
  render(<OperatorDashboard />);

  expect(await screen.findByText("source.create")).toBeInTheDocument();
  expect(screen.getByText("Usage breakdown")).toBeInTheDocument();
  expect(screen.getByText("Recent audit activity")).toBeInTheDocument();
  expect(screen.getByText("tokens")).toBeInTheDocument();
  expect(screen.getByText("25")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});

test("loads a trace by ID", async () => {
  const user = userEvent.setup();
  render(<OperatorDashboard />);
  await screen.findByText("source.create");

  await user.type(screen.getByLabelText("Trace ID"), "trace-1");
  await user.click(screen.getByRole("button", { name: "Load trace" }));

  expect(await screen.findByText("retrieval")).toBeInTheDocument();
  expect(screen.getByText('{"chunks":2}')).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/v1/operator/traces/trace-1",
    expect.objectContaining({ headers: expect.any(Object) }),
  );
});

test("renders a trace lookup error", async () => {
  const user = userEvent.setup();
  render(<OperatorDashboard />);
  await screen.findByText("source.create");

  await user.type(screen.getByLabelText("Trace ID"), "missing");
  await user.click(screen.getByRole("button", { name: "Load trace" }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Trace not found"));
});

test("renders useful empty states for first-run operator data", async () => {
  jest.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = input.toString();
    if (url.endsWith("/v1/operator/health")) {
      return jsonResponse({ tenant_id: "demo-tenant", trace_count: 0, audit_count: 0, usage: {}, status: "ok" });
    }
    if (url.endsWith("/v1/operator/usage")) {
      return jsonResponse({});
    }
    if (url.endsWith("/v1/operator/audit")) {
      return jsonResponse([]);
    }
    return jsonResponse({ detail: "Trace not found" }, 404);
  });

  render(<OperatorDashboard />);

  expect(await screen.findByText("No usage events yet. Ask a question in Chat to populate this panel.")).toBeInTheDocument();
  expect(screen.getByText("No audit activity yet. Source changes and sync actions will appear here.")).toBeInTheDocument();
  expect(screen.getByText("Paste a trace ID from a chat answer to inspect policy, retrieval, model, and citation stages.")).toBeInTheDocument();
});

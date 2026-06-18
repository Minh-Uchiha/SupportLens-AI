import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SourceAdmin } from "./SourceAdmin";

const source = {
  id: "source-1",
  tenant_id: "demo-tenant",
  type: "inline",
  name: "Runbook",
  connection_ref: "SL-429 runbook text",
  status: "enabled",
  sync_policy: "manual",
  permission_mode: "tenant",
  last_sync_at: null,
  last_sync_status: "success",
  last_failure_reason: null,
};

function jsonResponse(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  } as Response);
}

function installSourceFetchMock(empty = false) {
  global.fetch = jest.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    if (url.endsWith("/v1/admin/sources") && init?.method === "POST") {
      return jsonResponse({ ...source, id: "source-2", name: "New Source" });
    }
    if (url.endsWith("/v1/admin/sources")) {
      return jsonResponse(empty ? [] : [source]);
    }
    if (url.endsWith("/v1/admin/sources/jobs/list")) {
      return jsonResponse(
        empty
          ? []
          : [
              {
                id: "job-1",
                tenant_id: "demo-tenant",
                source_id: "source-1",
                job_type: "initial_sync",
                status: "completed",
                reason: null,
                created_at: "2026-01-01T00:00:00",
              },
            ],
      );
    }
    if (url.endsWith("/v1/admin/sources/source-1/health")) {
      return jsonResponse({
        source_id: "source-1",
        status: "enabled",
        last_sync: null,
        last_sync_status: "success",
        failure_reason: null,
        document_count: 1,
        chunk_count: 2,
        freshness: "fresh",
      });
    }
    if (url.endsWith("/v1/admin/sources/source-1/sync") || url.endsWith("/v1/admin/sources/source-2/sync")) {
      return jsonResponse({
        id: "job-2",
        tenant_id: "demo-tenant",
        source_id: url.includes("source-2") ? "source-2" : "source-1",
        job_type: "manual_resync",
        status: "completed",
        reason: "manual_resync",
        created_at: "2026-01-01T00:00:00",
      });
    }
    if (url.endsWith("/v1/admin/sources/source-1/reembed")) {
      return jsonResponse({
        id: "job-3",
        tenant_id: "demo-tenant",
        source_id: "source-1",
        job_type: "reembed",
        status: "completed",
        reason: "reembed",
        created_at: "2026-01-01T00:00:00",
      });
    }
    if (url.endsWith("/v1/admin/sources/source-1") && init?.method === "PATCH") {
      return jsonResponse({ ...source, status: "disabled" });
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      statusText: "Not found",
      json: async () => ({ detail: "Not found" }),
    } as Response);
  });
}

beforeEach(() => {
  installSourceFetchMock();
});

afterEach(() => {
  jest.resetAllMocks();
});

test("renders source configuration controls and source health", async () => {
  render(<SourceAdmin />);

  expect(await screen.findByRole("button", { name: /New source/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Create source/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Create and sync/i })).toBeInTheDocument();
  expect(await screen.findByText("Runbook")).toBeInTheDocument();
  expect(screen.getByText("1")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(screen.getByText("initial sync")).toBeInTheDocument();
});

test("creates and immediately syncs a source", async () => {
  const user = userEvent.setup();
  render(<SourceAdmin />);
  await screen.findByText("Runbook");

  await user.clear(screen.getByLabelText("Source name"));
  await user.type(screen.getByLabelText("Source name"), "New Source");
  await user.type(screen.getByLabelText("Inline source text"), "Fresh support article");
  await user.click(screen.getByRole("button", { name: /Create and sync/i }));

  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/admin/sources/source-2/sync",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ sync_reason: "initial_sync" }) }),
    ),
  );
});

test("runs source actions from visible buttons", async () => {
  const user = userEvent.setup();
  render(<SourceAdmin />);
  await screen.findByText("Runbook");

  await user.click(screen.getByRole("button", { name: /Sync now/i }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/admin/sources/source-1/sync",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ sync_reason: "manual_resync" }) }),
    ),
  );

  await user.click(screen.getByRole("button", { name: /Retry sync/i }));
  await user.click(screen.getByRole("button", { name: /Permission refresh/i }));
  await user.click(screen.getByRole("button", { name: /Re-embed/i }));
  await user.click(screen.getByRole("button", { name: /Disable/i }));

  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/v1/admin/sources/source-1/reembed",
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/v1/admin/sources/source-1",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "disabled" }) }),
  );
});

test("renders an empty source state", async () => {
  installSourceFetchMock(true);

  render(<SourceAdmin />);
  expect(await screen.findByText("No sources yet")).toBeInTheDocument();
  expect(screen.getByText("Create an inline runbook or URL source, then sync it so chat can retrieve citations.")).toBeInTheDocument();
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatShell } from "./ChatShell";
import { AnswerCard } from "./AnswerCard";
import type { AnswerResponse } from "../../lib/api";

const answeredResponse: AnswerResponse = {
  answer_id: "answer-1",
  conversation_id: "conversation-1",
  answer_state: "answered",
  answer_text: "Check usage and retry after the backoff window.",
  citations: [
    {
      chunk_id: "chunk-1",
      source_id: "source-1",
      document_id: "doc-1",
      citation_anchor: "Runbook#chunk-1",
      snippet: "Resolve SL-429 by checking usage and retrying after backoff.",
    },
  ],
  evidence: [],
  trace_id: "trace-1",
};

function mockJson(body: unknown, init?: ResponseInit) {
  const status = init?.status ?? 200;
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: init?.statusText ?? "",
    json: async () => body,
  } as Response);
}

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.resetAllMocks();
});

test("submits a question through the messenger composer and renders answer citations", async () => {
  const user = userEvent.setup();
  let resolveAnswer: (response: Response) => void = () => undefined;
  jest.mocked(fetch).mockReturnValueOnce(
    new Promise<Response>((resolve) => {
      resolveAnswer = resolve;
    }),
  );

  render(<ChatShell />);
  await user.click(screen.getByRole("button", { name: "Send question" }));

  expect(screen.getByText("How do I resolve SL-429?")).toBeInTheDocument();
  expect(screen.getByRole("status")).toBeInTheDocument();
  resolveAnswer(await mockJson(answeredResponse));

  expect(await screen.findByText("Check usage and retry after the backoff window.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Runbook#chunk-1" })).toBeInTheDocument();
  expect(screen.getByText("source-1")).toBeInTheDocument();
});

test("keeps prior turns and sends follow-up questions with the conversation id", async () => {
  const user = userEvent.setup();
  jest.mocked(fetch)
    .mockReturnValueOnce(mockJson(answeredResponse))
    .mockReturnValueOnce(mockJson({ ...answeredResponse, answer_id: "answer-2", answer_text: "Use the retry window again." }));

  render(<ChatShell />);
  await user.click(screen.getByRole("button", { name: "Send question" }));
  await screen.findByText("Check usage and retry after the backoff window.");

  await user.type(screen.getByLabelText("Support question"), "What about retries?");
  await user.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByText("Use the retry window again.")).toBeInTheDocument();
  expect(screen.getByText("How do I resolve SL-429?")).toBeInTheDocument();
  expect(fetch).toHaveBeenLastCalledWith(
    "http://localhost:8000/v1/chat/messages",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ conversation_id: "conversation-1", message: "What about retries?" }),
    }),
  );
});

test("renders refusal without exposing citation details when no citations return", async () => {
  const user = userEvent.setup();
  jest.mocked(fetch).mockReturnValueOnce(
    mockJson({
      ...answeredResponse,
      answer_state: "refused_no_evidence",
      answer_text: "I do not have evidence for that.",
      citations: [],
    }),
  );

  render(<ChatShell />);
  await user.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByText("No evidence")).toBeInTheDocument();
  expect(screen.getByText("No citations are available because no supporting evidence was found.")).toBeInTheDocument();
  expect(screen.queryByText("source-1")).not.toBeInTheDocument();
});

test("renders network errors", async () => {
  const user = userEvent.setup();
  jest.mocked(fetch).mockRejectedValueOnce(new Error("Network down"));

  render(<ChatShell />);
  await user.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Network down");
});

test("renders partial and citation validation failed states", () => {
  const onSelectCitation = jest.fn();
  const { rerender } = render(
    <AnswerCard
      answer={{ ...answeredResponse, answer_state: "partial", answer_text: "Only part of this is supported." }}
      onSelectCitation={onSelectCitation}
      selectedCitationId="chunk-1"
    />,
  );
  expect(screen.getByText("Partial answer")).toBeInTheDocument();

  rerender(
    <AnswerCard
      answer={{
        ...answeredResponse,
        answer_state: "citation_validation_failed",
        answer_text: "Citation validation failed.",
        citations: [],
      }}
      onSelectCitation={onSelectCitation}
      selectedCitationId={null}
    />,
  );
  expect(screen.getByText("Citation validation failed")).toBeInTheDocument();
  expect(screen.getByText("Citations are hidden because validation failed.")).toBeInTheDocument();
});

test("submits feedback for the selected answer", async () => {
  const user = userEvent.setup();
  jest.mocked(fetch)
    .mockReturnValueOnce(mockJson(answeredResponse))
    .mockReturnValueOnce(mockJson({ id: "feedback-1" }));

  render(<ChatShell />);
  await user.click(screen.getByRole("button", { name: "Send question" }));
  await screen.findByText("Check usage and retry after the backoff window.");
  await user.click(screen.getByRole("button", { name: "Submit feedback" }));

  await waitFor(() => expect(screen.getByText("Feedback submitted.")).toBeInTheDocument());
  expect(fetch).toHaveBeenLastCalledWith(
    "http://localhost:8000/v1/feedback",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        answer_id: "answer-1",
        citation_id: "chunk-1",
        feedback_type: "helpful",
        comment: null,
      }),
    }),
  );
});

"use client";

import { FormEvent, useState } from "react";
import { SendHorizontal } from "lucide-react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { postChatMessage, type AnswerResponse, type Citation } from "../../lib/api";
import { AnswerCard } from "./AnswerCard";

type ThreadMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; answer: AnswerResponse; selectedCitationId: string | null };

export function ChatShell() {
  const [draft, setDraft] = useState("How do I resolve SL-429?");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || status === "loading") {
      return;
    }

    const userMessage: ThreadMessage = { id: `user-${Date.now()}`, role: "user", text: trimmed };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setStatus("loading");
    setError(null);

    try {
      const response = await postChatMessage({ conversation_id: conversationId, message: trimmed });
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: response.answer_id,
          role: "assistant",
          answer: response,
          selectedCitationId: response.citations[0]?.chunk_id ?? null,
        },
      ]);
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "The chat request failed.");
    }
  }

  function onSelectCitation(messageId: string, citation: Citation) {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId && message.role === "assistant"
          ? { ...message, selectedCitationId: citation.chunk_id }
          : message,
      ),
    );
  }

  return (
    <main className="chat-page">
      <section className="chat-shell" aria-label="Support chat">
        <header className="chat-header">
          <div>
            <span className="eyebrow">Grounded answer workspace</span>
            <h1>Support chat</h1>
          </div>
          <span className="badge neutral">{conversationId ? "conversation active" : "new conversation"}</span>
        </header>

        <div className="message-thread" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-thread">
              <h2>Start with a support question</h2>
              <p>Answers will appear here with citations, trace IDs, and feedback controls attached to each response.</p>
            </div>
          ) : null}

          {messages.map((message) =>
            message.role === "user" ? (
              <article className="message-row user" key={message.id}>
                <div className="message-bubble user-bubble">
                  <p>{message.text}</p>
                  <span>You</span>
                </div>
              </article>
            ) : (
              <article className="message-row assistant" key={message.id}>
                <div className="message-bubble assistant-bubble">
                  <AnswerCard
                    answer={message.answer}
                    onSelectCitation={(citation) => onSelectCitation(message.id, citation)}
                    selectedCitationId={message.selectedCitationId}
                  />
                  <FeedbackControls
                    answerId={message.answer.answer_id}
                    citations={message.answer.citations}
                    selectedCitationId={message.selectedCitationId}
                  />
                </div>
              </article>
            ),
          )}

          {status === "loading" ? (
            <article className="message-row assistant">
              <div className="typing-bubble" role="status">
                <span />
                <span />
                <span />
              </div>
            </article>
          ) : null}
        </div>

        {error ? <p className="error composer-error" role="alert">{error}</p> : null}
        <form className="chat-composer" onSubmit={onSubmit}>
          <textarea
            aria-label="Support question"
            disabled={status === "loading"}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Type your support question..."
            rows={1}
            value={draft}
          />
          <button aria-label="Send question" disabled={status === "loading" || !draft.trim()} type="submit">
            <SendHorizontal size={20} />
            <span>Send</span>
          </button>
        </form>
      </section>
    </main>
  );
}

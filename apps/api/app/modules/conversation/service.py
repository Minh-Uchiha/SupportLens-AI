from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, status

from app.modules.auth_policy.schemas import RequestContext
from app.modules.auth_policy.service import enforce_tenant_scope
from app.modules.conversation.schemas import (
    ConversationCreate,
    ConversationRecord,
    FeedbackCreate,
    FeedbackRecord,
    MessageRecord,
    StoredAnswer,
)
from app.modules.telemetry.service import record_usage

_conversations: dict[str, ConversationRecord] = {}
_messages: dict[str, MessageRecord] = {}
_answers: dict[str, StoredAnswer] = {}
_feedback: dict[str, FeedbackRecord] = {}


def reset_conversation_store() -> None:
    _conversations.clear()
    _messages.clear()
    _answers.clear()
    _feedback.clear()


def create_conversation(context: RequestContext, payload: ConversationCreate | None = None) -> ConversationRecord:
    record = ConversationRecord(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        title=(payload.title if payload and payload.title else "New conversation"),
    )
    _conversations[record.id] = record
    record_usage(context, "conversation", 1)
    return record


def list_conversations(context: RequestContext) -> list[ConversationRecord]:
    return [item for item in _conversations.values() if item.tenant_id == context.tenant_id and item.user_id == context.user_id]


def get_conversation(context: RequestContext, conversation_id: str) -> ConversationRecord:
    conversation = _conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    enforce_tenant_scope(context, conversation.tenant_id)
    if conversation.user_id != context.user_id and not context.roles.intersection({"tenant_admin", "platform_operator"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conversation belongs to another user")
    return conversation


def add_message(context: RequestContext, conversation_id: str, role: str, content: str) -> MessageRecord:
    get_conversation(context, conversation_id)
    message = MessageRecord(id=str(uuid4()), conversation_id=conversation_id, role=role, content=content)
    _messages[message.id] = message
    record_usage(context, f"message.{role}", 1)
    return message


def store_answer(context: RequestContext, conversation_id: str, message_id: str, answer_state: str, text: str, trace_id: str, citation_ids: list[str]) -> StoredAnswer:
    get_conversation(context, conversation_id)
    answer = StoredAnswer(
        id=str(uuid4()), conversation_id=conversation_id, message_id=message_id,
        answer_state=answer_state, text=text, trace_id=trace_id, citation_ids=citation_ids,
    )
    _answers[answer.id] = answer
    record_usage(context, f"answer.{answer_state}", 1)
    return answer


def get_answer(context: RequestContext, answer_id: str) -> StoredAnswer:
    answer = _answers.get(answer_id)
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found")
    get_conversation(context, answer.conversation_id)
    return answer


def get_conversation_detail(context: RequestContext, conversation_id: str) -> dict[str, object]:
    conversation = get_conversation(context, conversation_id)
    messages = [message for message in _messages.values() if message.conversation_id == conversation_id]
    answers = [answer for answer in _answers.values() if answer.conversation_id == conversation_id]
    return {"conversation": conversation, "messages": messages, "answers": answers}


def conversation_context(context: RequestContext, conversation_id: str) -> list[str]:
    get_conversation(context, conversation_id)
    return [message.content for message in _messages.values() if message.conversation_id == conversation_id]


def submit_feedback(context: RequestContext, payload: FeedbackCreate) -> FeedbackRecord:
    answer = get_answer(context, payload.answer_id)
    feedback = FeedbackRecord(
        id=str(uuid4()), tenant_id=context.tenant_id, answer_id=answer.id,
        citation_id=payload.citation_id, feedback_type=payload.feedback_type, comment=payload.comment,
    )
    _feedback[feedback.id] = feedback
    record_usage(context, "feedback", 1)
    return feedback


def list_feedback(context: RequestContext) -> list[FeedbackRecord]:
    return [item for item in _feedback.values() if item.tenant_id == context.tenant_id]

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from app.db.models import AnswerCitationRow, AnswerRow, ConversationRow, FeedbackRow, MessageRow
from app.db.session import current_session
from app.modules.auth_policy.schemas import RequestContext, Role
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


def _to_conversation(row: ConversationRow) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        title=row.title,
        status=row.status,
        created_at=row.created_at,
    )


def _to_message(row: MessageRow) -> MessageRecord:
    return MessageRecord(id=row.id, conversation_id=row.conversation_id, role=row.role, content=row.content, created_at=row.created_at)


def _to_answer(row: AnswerRow) -> StoredAnswer:
    session = current_session()
    citation_ids = list(session.scalars(select(AnswerCitationRow.chunk_id).where(AnswerCitationRow.answer_id == row.id)))
    return StoredAnswer(
        id=row.id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        answer_state=row.answer_state,
        text=row.text,
        trace_id=row.trace_id,
        citation_ids=citation_ids,
    )


def _to_feedback(row: FeedbackRow) -> FeedbackRecord:
    return FeedbackRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        answer_id=row.answer_id,
        citation_id=row.citation_id,
        feedback_type=row.feedback_type,
        comment=row.comment,
        created_at=row.created_at,
    )


def reset_conversation_store() -> None:
    session = current_session()
    session.execute(delete(FeedbackRow))
    session.execute(delete(AnswerCitationRow))
    session.execute(delete(AnswerRow))
    session.execute(delete(MessageRow))
    session.execute(delete(ConversationRow))


def create_conversation(context: RequestContext, payload: ConversationCreate | None = None) -> ConversationRecord:
    row = ConversationRow(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        title=(payload.title if payload and payload.title else "New conversation"),
    )
    session = current_session()
    session.add(row)
    session.flush()
    record_usage(context, "conversation", 1)
    return _to_conversation(row)


def list_conversations(context: RequestContext) -> list[ConversationRecord]:
    session = current_session()
    rows = session.scalars(
        select(ConversationRow)
        .where(ConversationRow.tenant_id == context.tenant_id, ConversationRow.user_id == context.user_id)
        .order_by(ConversationRow.created_at)
    )
    return [_to_conversation(row) for row in rows]


def _get_conversation_row(context: RequestContext, conversation_id: str) -> ConversationRow:
    row = current_session().get(ConversationRow, conversation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    enforce_tenant_scope(context, row.tenant_id)
    if row.user_id != context.user_id and not context.has_role({Role.tenant_admin, Role.platform_operator}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conversation belongs to another user")
    return row


def get_conversation(context: RequestContext, conversation_id: str) -> ConversationRecord:
    return _to_conversation(_get_conversation_row(context, conversation_id))


def add_message(context: RequestContext, conversation_id: str, role: str, content: str) -> MessageRecord:
    _get_conversation_row(context, conversation_id)
    message = MessageRow(id=str(uuid4()), conversation_id=conversation_id, role=role, content=content)
    session = current_session()
    session.add(message)
    session.flush()
    record_usage(context, f"message.{role}", 1)
    return _to_message(message)


def store_answer(context: RequestContext, conversation_id: str, message_id: str, answer_state: str, text: str, trace_id: str, citation_ids: list[str]) -> StoredAnswer:
    _get_conversation_row(context, conversation_id)
    answer = AnswerRow(
        id=str(uuid4()), conversation_id=conversation_id, message_id=message_id,
        answer_state=answer_state, text=text, trace_id=trace_id,
    )
    session = current_session()
    session.add(answer)
    session.flush()
    for citation_id in citation_ids:
        session.add(AnswerCitationRow(answer_id=answer.id, chunk_id=citation_id))
    session.flush()
    record_usage(context, f"answer.{answer_state}", 1)
    return _to_answer(answer)


def get_answer(context: RequestContext, answer_id: str) -> StoredAnswer:
    answer = current_session().get(AnswerRow, answer_id)
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found")
    get_conversation(context, answer.conversation_id)
    return _to_answer(answer)


def get_conversation_detail(context: RequestContext, conversation_id: str) -> dict[str, object]:
    conversation = _to_conversation(_get_conversation_row(context, conversation_id))
    session = current_session()
    messages = [
        _to_message(message)
        for message in session.scalars(select(MessageRow).where(MessageRow.conversation_id == conversation_id).order_by(MessageRow.created_at))
    ]
    answers = [
        _to_answer(answer)
        for answer in session.scalars(select(AnswerRow).where(AnswerRow.conversation_id == conversation_id).order_by(AnswerRow.created_at))
    ]
    return {"conversation": conversation, "messages": messages, "answers": answers}


def conversation_context(context: RequestContext, conversation_id: str) -> list[str]:
    _get_conversation_row(context, conversation_id)
    session = current_session()
    messages = list(session.scalars(select(MessageRow).where(MessageRow.conversation_id == conversation_id).order_by(MessageRow.created_at)))
    answers_by_message_id = {
        answer.message_id: answer
        for answer in session.scalars(select(AnswerRow).where(AnswerRow.conversation_id == conversation_id).order_by(AnswerRow.created_at))
    }
    turns: list[str] = []
    for message in messages:
        turns.append(f"User: {message.content}")
        answer = answers_by_message_id.get(message.id)
        if answer is not None:
            turns.append(f"Assistant ({answer.answer_state}): {answer.text}")
    return turns[-8:]


def submit_feedback(context: RequestContext, payload: FeedbackCreate) -> FeedbackRecord:
    answer = get_answer(context, payload.answer_id)
    feedback = FeedbackRow(
        id=str(uuid4()), tenant_id=context.tenant_id, answer_id=answer.id,
        citation_id=payload.citation_id, feedback_type=payload.feedback_type, comment=payload.comment,
    )
    session = current_session()
    session.add(feedback)
    session.flush()
    record_usage(context, "feedback", 1)
    return _to_feedback(feedback)


def list_feedback(context: RequestContext) -> list[FeedbackRecord]:
    return [
        _to_feedback(item)
        for item in current_session().scalars(select(FeedbackRow).where(FeedbackRow.tenant_id == context.tenant_id).order_by(FeedbackRow.created_at))
    ]

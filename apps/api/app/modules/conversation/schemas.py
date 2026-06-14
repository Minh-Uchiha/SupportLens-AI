from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRecord(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StoredAnswer(BaseModel):
    id: str
    conversation_id: str
    message_id: str
    answer_state: str
    text: str
    trace_id: str
    citation_ids: list[str] = Field(default_factory=list)


class FeedbackCreate(BaseModel):
    answer_id: str
    citation_id: str | None = None
    feedback_type: str
    comment: str | None = None


class FeedbackRecord(BaseModel):
    id: str
    tenant_id: str
    answer_id: str
    citation_id: str | None = None
    feedback_type: str
    comment: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

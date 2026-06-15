from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    retention_policy: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    external_subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")


class TenantMembershipRow(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "role", name="uq_tenant_membership_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")


class TenantPolicyRow(Base):
    __tablename__ = "tenant_policies"

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), primary_key=True)
    citation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retention_settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    logging_posture: Mapped[str] = mapped_column(String, nullable=False, default="redacted")


class KnowledgeSourceRow(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    connection_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="enabled")
    sync_policy: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    permission_mode: Mapped[str] = mapped_column(String, nullable=False, default="tenant")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str] = mapped_column(String, nullable=False, default="never_synced")
    last_failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SourceDocumentRow(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    freshness_status: Mapped[str] = mapped_column(String, nullable=False, default="fresh")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    acl_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("source_documents.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_anchor: Mapped[str] = mapped_column(Text, nullable=False)
    acl_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)


class IngestionJobRow(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AnswerRow(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), nullable=False, index=True)
    answer_state: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AnswerCitationRow(Base):
    __tablename__ = "answer_citations"
    __table_args__ = (UniqueConstraint("answer_id", "chunk_id", name="uq_answer_citation_chunk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    answer_id: Mapped[str] = mapped_column(String, ForeignKey("answers.id"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_chunks.id"), nullable=False)


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    answer_id: Mapped[str] = mapped_column(String, ForeignKey("answers.id"), nullable=False, index=True)
    citation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    feedback_type: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AnswerTraceRow(Base):
    __tablename__ = "answer_traces"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    answer_state: Mapped[str] = mapped_column(String, nullable=False, default="started")
    redaction_status: Mapped[str] = mapped_column(String, nullable=False, default="redacted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AnswerTraceStageRow(Base):
    __tablename__ = "answer_trace_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String, ForeignKey("answer_traces.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    stage_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UsageEventRow(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class EvaluationSetRow(Base):
    __tablename__ = "evaluation_sets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    scenario_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ready")


class EvaluationResultRow(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    evaluation_set_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_sets.id"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

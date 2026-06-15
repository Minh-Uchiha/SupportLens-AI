from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_persistence"
down_revision = None
branch_labels = None
depends_on = None


def _jsonb_default() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("retention_policy", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("external_subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "role", name="uq_tenant_membership_role"),
    )
    op.create_table(
        "tenant_policies",
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("citation_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retention_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("logging_posture", sa.String(), nullable=False, server_default="redacted"),
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("connection_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="enabled"),
        sa.Column("sync_policy", sa.String(), nullable=False),
        sa.Column("permission_mode", sa.String(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(), nullable=False, server_default="never_synced"),
        sa.Column("last_failure_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_knowledge_sources_tenant_id", "knowledge_sources", ["tenant_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("freshness_status", sa.String(), nullable=False, server_default="fresh"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("acl_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
    )
    op.create_index("ix_source_documents_tenant_id", "source_documents", ["tenant_id"])
    op.create_index("ix_source_documents_source_id", "source_documents", ["source_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("citation_anchor", sa.Text(), nullable=False),
        sa.Column("acl_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_knowledge_chunks_tenant_id", "knowledge_chunks", ["tenant_id"])
    op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ingestion_jobs_tenant_id", "ingestion_jobs", ["tenant_id"])
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "answers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("message_id", sa.String(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("answer_state", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_answers_conversation_id", "answers", ["conversation_id"])
    op.create_index("ix_answers_message_id", "answers", ["message_id"])
    op.create_index("ix_answers_trace_id", "answers", ["trace_id"])

    op.create_table(
        "answer_citations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("answer_id", sa.String(), sa.ForeignKey("answers.id"), nullable=False),
        sa.Column("chunk_id", sa.String(), sa.ForeignKey("knowledge_chunks.id"), nullable=False),
        sa.UniqueConstraint("answer_id", "chunk_id", name="uq_answer_citation_chunk"),
    )
    op.create_index("ix_answer_citations_answer_id", "answer_citations", ["answer_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("answer_id", sa.String(), sa.ForeignKey("answers.id"), nullable=False),
        sa.Column("citation_id", sa.String(), nullable=True),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_feedback_tenant_id", "feedback", ["tenant_id"])
    op.create_index("ix_feedback_answer_id", "feedback", ["answer_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])

    op.create_table(
        "answer_traces",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("answer_state", sa.String(), nullable=False, server_default="started"),
        sa.Column("redaction_status", sa.String(), nullable=False, server_default="redacted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_answer_traces_tenant_id", "answer_traces", ["tenant_id"])
    op.create_index("ix_answer_traces_conversation_id", "answer_traces", ["conversation_id"])

    op.create_table(
        "answer_trace_stages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(), sa.ForeignKey("answer_traces.id"), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_answer_trace_stages_trace_id", "answer_trace_stages", ["trace_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("cost_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_usage_events_tenant_id", "usage_events", ["tenant_id"])

    op.create_table(
        "evaluation_sets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scenario_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
    )
    op.create_index("ix_evaluation_sets_tenant_id", "evaluation_sets", ["tenant_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("evaluation_set_id", sa.String(), sa.ForeignKey("evaluation_sets.id"), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("run_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_evaluation_results_tenant_id", "evaluation_results", ["tenant_id"])
    op.create_index("ix_evaluation_results_evaluation_set_id", "evaluation_results", ["evaluation_set_id"])


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_evaluation_results_evaluation_set_id", "evaluation_results"),
        ("ix_evaluation_results_tenant_id", "evaluation_results"),
        ("ix_evaluation_sets_tenant_id", "evaluation_sets"),
        ("ix_usage_events_tenant_id", "usage_events"),
        ("ix_answer_trace_stages_trace_id", "answer_trace_stages"),
        ("ix_answer_traces_conversation_id", "answer_traces"),
        ("ix_answer_traces_tenant_id", "answer_traces"),
        ("ix_audit_events_tenant_id", "audit_events"),
        ("ix_feedback_answer_id", "feedback"),
        ("ix_feedback_tenant_id", "feedback"),
        ("ix_answer_citations_answer_id", "answer_citations"),
        ("ix_answers_trace_id", "answers"),
        ("ix_answers_message_id", "answers"),
        ("ix_answers_conversation_id", "answers"),
        ("ix_messages_conversation_id", "messages"),
        ("ix_conversations_user_id", "conversations"),
        ("ix_conversations_tenant_id", "conversations"),
        ("ix_ingestion_jobs_source_id", "ingestion_jobs"),
        ("ix_ingestion_jobs_tenant_id", "ingestion_jobs"),
        ("ix_knowledge_chunks_document_id", "knowledge_chunks"),
        ("ix_knowledge_chunks_source_id", "knowledge_chunks"),
        ("ix_knowledge_chunks_tenant_id", "knowledge_chunks"),
        ("ix_source_documents_source_id", "source_documents"),
        ("ix_source_documents_tenant_id", "source_documents"),
        ("ix_knowledge_sources_tenant_id", "knowledge_sources"),
    ]:
        op.drop_index(index_name, table_name=table_name)

    for table_name in [
        "evaluation_results",
        "evaluation_sets",
        "usage_events",
        "answer_trace_stages",
        "answer_traces",
        "audit_events",
        "feedback",
        "answer_citations",
        "answers",
        "messages",
        "conversations",
        "ingestion_jobs",
        "knowledge_chunks",
        "source_documents",
        "knowledge_sources",
        "tenant_policies",
        "tenant_memberships",
        "users",
        "tenants",
    ]:
        op.drop_table(table_name)

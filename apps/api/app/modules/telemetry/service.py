from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models import AnswerTraceRow, AnswerTraceStageRow, AuditEventRow, UsageEventRow
from app.db.session import current_session
from app.modules.auth_policy.schemas import RequestContext


@dataclass
class AuditEvent:
    id: str
    tenant_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AnswerTrace:
    id: str
    tenant_id: str
    conversation_id: str | None
    stages: list[dict[str, Any]] = field(default_factory=list)
    answer_state: str = "started"
    redaction_status: str = "redacted"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UsageEvent:
    id: str
    tenant_id: str
    event_type: str
    quantity: int
    cost_metadata: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _to_audit_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        actor_id=row.actor_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        created_at=row.created_at,
    )


def _trace_stages(trace_id: str) -> list[dict[str, Any]]:
    rows = current_session().scalars(
        select(AnswerTraceStageRow).where(AnswerTraceStageRow.trace_id == trace_id).order_by(AnswerTraceStageRow.created_at, AnswerTraceStageRow.id)
    )
    return [
        {"stage": row.stage, "metadata": row.stage_metadata, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


def _to_trace(row: AnswerTraceRow) -> AnswerTrace:
    return AnswerTrace(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        stages=_trace_stages(row.id),
        answer_state=row.answer_state,
        redaction_status=row.redaction_status,
        created_at=row.created_at,
    )


def _to_usage_event(row: UsageEventRow) -> UsageEvent:
    return UsageEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        event_type=row.event_type,
        quantity=row.quantity,
        cost_metadata=row.cost_metadata,
        created_at=row.created_at,
    )


def reset_telemetry_store() -> None:
    session = current_session()
    session.execute(delete(AnswerTraceStageRow))
    session.execute(delete(AnswerTraceRow))
    session.execute(delete(AuditEventRow))
    session.execute(delete(UsageEventRow))


def write_audit_event(context: RequestContext, action: str, resource_type: str, resource_id: str) -> AuditEvent:
    event = AuditEventRow(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    session = current_session()
    session.add(event)
    session.flush()
    return _to_audit_event(event)


def start_trace(context: RequestContext, conversation_id: str | None) -> AnswerTrace:
    trace = AnswerTraceRow(id=str(uuid4()), tenant_id=context.tenant_id, conversation_id=conversation_id)
    session = current_session()
    session.add(trace)
    session.flush()
    add_trace_stage(trace.id, "policy", {"tenant_id": context.tenant_id, "roles": sorted(context.roles)})
    return _to_trace(trace)


def add_trace_stage(trace_id: str, stage: str, metadata: dict[str, Any]) -> None:
    current_session().add(AnswerTraceStageRow(trace_id=trace_id, stage=stage, stage_metadata=metadata))


def finish_trace(trace_id: str, answer_state: str) -> AnswerTrace:
    trace = current_session().get(AnswerTraceRow, trace_id)
    if trace is None:
        raise KeyError(trace_id)
    trace.answer_state = answer_state
    current_session().flush()
    return _to_trace(trace)


def record_usage(context: RequestContext, event_type: str, quantity: int, cost_metadata: dict[str, Any] | None = None) -> UsageEvent:
    event = UsageEventRow(id=str(uuid4()), tenant_id=context.tenant_id, event_type=event_type, quantity=quantity, cost_metadata=cost_metadata or {})
    session = current_session()
    session.add(event)
    session.flush()
    return _to_usage_event(event)


def get_trace_for_context(context: RequestContext, trace_id: str) -> AnswerTrace | None:
    trace = current_session().get(AnswerTraceRow, trace_id)
    if trace is None or trace.tenant_id != context.tenant_id:
        return None
    return _to_trace(trace)


def list_audit_for_context(context: RequestContext) -> list[AuditEvent]:
    rows = current_session().scalars(
        select(AuditEventRow).where(AuditEventRow.tenant_id == context.tenant_id).order_by(AuditEventRow.created_at)
    )
    return [_to_audit_event(event) for event in rows]


def usage_summary(context: RequestContext) -> dict[str, int]:
    summary: dict[str, int] = {}
    rows = current_session().scalars(select(UsageEventRow).where(UsageEventRow.tenant_id == context.tenant_id))
    for event in rows:
        summary[event.event_type] = summary.get(event.event_type, 0) + event.quantity
    return summary


def health_summary(context: RequestContext) -> dict[str, Any]:
    trace_count = len(list(current_session().scalars(select(AnswerTraceRow.id).where(AnswerTraceRow.tenant_id == context.tenant_id))))
    return {
        "tenant_id": context.tenant_id,
        "trace_count": trace_count,
        "audit_count": len(list_audit_for_context(context)),
        "usage": usage_summary(context),
        "status": "ok",
    }

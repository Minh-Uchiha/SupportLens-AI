from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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


_audit_events: dict[str, AuditEvent] = {}
_answer_traces: dict[str, AnswerTrace] = {}
_usage_events: dict[str, UsageEvent] = {}


def reset_telemetry_store() -> None:
    _audit_events.clear()
    _answer_traces.clear()
    _usage_events.clear()


def write_audit_event(context: RequestContext, action: str, resource_type: str, resource_id: str) -> AuditEvent:
    event = AuditEvent(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    _audit_events[event.id] = event
    return event


def start_trace(context: RequestContext, conversation_id: str | None) -> AnswerTrace:
    trace = AnswerTrace(id=str(uuid4()), tenant_id=context.tenant_id, conversation_id=conversation_id)
    _answer_traces[trace.id] = trace
    add_trace_stage(trace.id, "policy", {"tenant_id": context.tenant_id, "roles": sorted(context.roles)})
    return trace


def add_trace_stage(trace_id: str, stage: str, metadata: dict[str, Any]) -> None:
    trace = _answer_traces[trace_id]
    trace.stages.append({"stage": stage, "metadata": metadata, "created_at": datetime.now(timezone.utc).isoformat()})


def finish_trace(trace_id: str, answer_state: str) -> AnswerTrace:
    trace = _answer_traces[trace_id]
    trace.answer_state = answer_state
    return trace


def record_usage(context: RequestContext, event_type: str, quantity: int, cost_metadata: dict[str, Any] | None = None) -> UsageEvent:
    event = UsageEvent(str(uuid4()), context.tenant_id, event_type, quantity, cost_metadata or {})
    _usage_events[event.id] = event
    return event


def get_trace_for_context(context: RequestContext, trace_id: str) -> AnswerTrace | None:
    trace = _answer_traces.get(trace_id)
    if trace is None or trace.tenant_id != context.tenant_id:
        return None
    return trace


def list_audit_for_context(context: RequestContext) -> list[AuditEvent]:
    return [event for event in _audit_events.values() if event.tenant_id == context.tenant_id]


def usage_summary(context: RequestContext) -> dict[str, int]:
    summary: dict[str, int] = {}
    for event in _usage_events.values():
        if event.tenant_id != context.tenant_id:
            continue
        summary[event.event_type] = summary.get(event.event_type, 0) + event.quantity
    return summary


def health_summary(context: RequestContext) -> dict[str, Any]:
    traces = [trace for trace in _answer_traces.values() if trace.tenant_id == context.tenant_id]
    return {
        "tenant_id": context.tenant_id,
        "trace_count": len(traces),
        "audit_count": len(list_audit_for_context(context)),
        "usage": usage_summary(context),
        "status": "ok",
    }

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.auth_policy.dependencies import require_role
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.telemetry.service import get_trace_for_context, health_summary, list_audit_for_context, usage_summary

router = APIRouter(prefix="/v1/operator", tags=["operator"])
operator_context = require_role(Role.platform_operator, Role.compliance_reviewer, Role.tenant_admin)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, context: RequestContext = Depends(operator_context)):
    trace = get_trace_for_context(context, trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return trace


@router.get("/usage")
def get_usage(context: RequestContext = Depends(operator_context)):
    return usage_summary(context)


@router.get("/health")
def get_operator_health(context: RequestContext = Depends(operator_context)):
    return health_summary(context)


@router.get("/audit")
def get_audit(context: RequestContext = Depends(operator_context)):
    return list_audit_for_context(context)

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.modules.auth_policy.dependencies import require_role
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.evaluation.service import create_evaluation_set, launch_gate_report, list_results, run_quality_evaluation

router = APIRouter(prefix="/v1/evaluation", tags=["evaluation"])
evaluator_context = require_role(Role.tenant_admin, Role.platform_operator, Role.content_owner)


class EvaluationSetCreate(BaseModel):
    name: str
    scenario_count: int


@router.post("/sets")
def post_evaluation_set(payload: EvaluationSetCreate, context: RequestContext = Depends(evaluator_context)):
    return create_evaluation_set(context, payload.name, payload.scenario_count)


@router.post("/sets/{evaluation_set_id}/run")
def post_evaluation_run(evaluation_set_id: str, context: RequestContext = Depends(evaluator_context)):
    return run_quality_evaluation(context, evaluation_set_id)


@router.get("/results")
def get_results(context: RequestContext = Depends(evaluator_context)):
    return list_results(context)


@router.get("/launch-gate")
def get_launch_gate(context: RequestContext = Depends(evaluator_context)):
    return launch_gate_report(context)

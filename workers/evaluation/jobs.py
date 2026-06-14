from __future__ import annotations

from app.modules.auth_policy.schemas import RequestContext
from app.modules.evaluation.service import run_quality_evaluation


def run_groundedness_eval(context: RequestContext, evaluation_set_id: str):
    return [result for result in run_quality_evaluation(context, evaluation_set_id) if result.metric == "groundedness"]


def run_citation_eval(context: RequestContext, evaluation_set_id: str):
    return [result for result in run_quality_evaluation(context, evaluation_set_id) if result.metric == "citation_correctness"]


def run_retrieval_eval(context: RequestContext, evaluation_set_id: str):
    return [result for result in run_quality_evaluation(context, evaluation_set_id) if result.metric == "retrieval_relevance"]

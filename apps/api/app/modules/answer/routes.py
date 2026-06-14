from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.answer.schemas import ChatMessageRequest
from app.modules.answer.service import generate_answer
from app.modules.auth_policy.dependencies import get_request_context
from app.modules.auth_policy.schemas import RequestContext

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/messages")
def post_message(payload: ChatMessageRequest, context: RequestContext = Depends(get_request_context)):
    return generate_answer(context, payload)

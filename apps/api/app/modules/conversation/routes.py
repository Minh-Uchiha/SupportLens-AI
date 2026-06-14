from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.auth_policy.dependencies import get_request_context
from app.modules.auth_policy.schemas import RequestContext
from app.modules.conversation.schemas import ConversationCreate, FeedbackCreate
from app.modules.conversation.service import (
    create_conversation,
    get_answer,
    get_conversation_detail,
    list_conversations,
    list_feedback,
    submit_feedback,
)

router = APIRouter(prefix="/v1", tags=["conversation"])


@router.post("/conversations")
def post_conversation(payload: ConversationCreate, context: RequestContext = Depends(get_request_context)):
    return create_conversation(context, payload)


@router.get("/conversations")
def get_conversations(context: RequestContext = Depends(get_request_context)):
    return list_conversations(context)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, context: RequestContext = Depends(get_request_context)):
    return get_conversation_detail(context, conversation_id)


@router.get("/answers/{answer_id}")
def get_answer_route(answer_id: str, context: RequestContext = Depends(get_request_context)):
    return get_answer(context, answer_id)


@router.post("/feedback")
def post_feedback(payload: FeedbackCreate, context: RequestContext = Depends(get_request_context)):
    return submit_feedback(context, payload)


@router.get("/feedback")
def get_feedback(context: RequestContext = Depends(get_request_context)):
    return list_feedback(context)

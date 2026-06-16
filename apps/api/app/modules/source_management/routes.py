from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.auth_policy.dependencies import require_role
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.source_management.service import (
    SourceCreate,
    SourcePatch,
    SyncRequest,
    create_source,
    delete_source,
    list_jobs,
    list_sources,
    reembed_source,
    source_health,
    trigger_sync,
    update_source,
)

router = APIRouter(prefix="/v1/admin/sources", tags=["sources"])
admin_context = require_role(Role.tenant_admin, Role.content_owner, Role.platform_operator)


@router.get("")
def get_sources(context: RequestContext = Depends(admin_context)):
    return list_sources(context)


@router.post("")
def post_source(payload: SourceCreate, context: RequestContext = Depends(admin_context)):
    return create_source(context, payload)


@router.patch("/{source_id}")
def patch_source(source_id: str, payload: SourcePatch, context: RequestContext = Depends(admin_context)):
    return update_source(context, source_id, payload)


@router.post("/{source_id}/sync")
def post_sync(source_id: str, payload: SyncRequest, context: RequestContext = Depends(admin_context)):
    return trigger_sync(context, source_id, payload)


@router.post("/{source_id}/reembed")
def post_reembed(source_id: str, context: RequestContext = Depends(admin_context)):
    return reembed_source(context, source_id)


@router.get("/{source_id}/health")
def get_source_health(source_id: str, context: RequestContext = Depends(admin_context)):
    return source_health(context, source_id)


@router.delete("/{source_id}")
def delete_source_route(source_id: str, delete_mode: str = "disable", context: RequestContext = Depends(admin_context)):
    return delete_source(context, source_id, delete_mode)


@router.get("/jobs/list")
def get_jobs(context: RequestContext = Depends(admin_context)):
    return list_jobs(context)

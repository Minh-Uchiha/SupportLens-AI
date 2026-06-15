from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.modules.auth_policy.schemas import AclFilter, RequestContext, Role, TenantPolicy

DEFAULT_TENANT = "demo-tenant"


def _parse_roles(value: str | None) -> set[Role]:
    if not value:
        return {Role.end_user}
    roles: set[Role] = set()
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            roles.add(Role(item))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Unknown role: {item}") from exc
    return roles or {Role.end_user}


def resolve_request_context(request: Request) -> RequestContext:
    # MVP auth is header-based; missing tenant/user context must fail closed.
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")
    if not tenant_id or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant and user headers are required")
    return RequestContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email=request.headers.get("x-user-email", "user@example.com"),
        roles=_parse_roles(request.headers.get("x-role")),
        policy=TenantPolicy(),
    )


def require_role_context(context: RequestContext, allowed_roles: set[Role]) -> RequestContext:
    if not context.has_role(allowed_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return context


def build_document_acl_filter(context: RequestContext, source_ids: set[str] | None = None) -> AclFilter:
    return AclFilter(
        tenant_id=context.tenant_id,
        allowed_source_ids=source_ids,
        user_id=context.user_id,
        roles=context.roles,
    )


def enforce_tenant_scope(context: RequestContext, resource_tenant_id: str) -> None:
    if context.tenant_id != resource_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")

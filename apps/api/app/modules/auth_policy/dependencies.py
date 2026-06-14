from __future__ import annotations

from collections.abc import Callable
from fastapi import Depends, Request

from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.auth_policy.service import require_role_context, resolve_request_context


def get_request_context(request: Request) -> RequestContext:
    return resolve_request_context(request)


def require_role(*allowed_roles: Role) -> Callable[[RequestContext], RequestContext]:
    allowed = set(allowed_roles)

    def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        return require_role_context(context, allowed)

    return dependency

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    end_user = "end_user"
    support_agent = "support_agent"
    tenant_admin = "tenant_admin"
    content_owner = "content_owner"
    platform_operator = "platform_operator"
    compliance_reviewer = "compliance_reviewer"


class TenantPolicy(BaseModel):
    citation_required: bool = True
    retention_days: int = 30
    logging_posture: str = "redacted"
    allow_stale_when_sync_fails: bool = True


class RequestContext(BaseModel):
    tenant_id: str
    user_id: str
    email: EmailStr = "user@example.com"
    roles: set[Role] = Field(default_factory=lambda: {Role.end_user})
    policy: TenantPolicy = Field(default_factory=TenantPolicy)

    def has_role(self, allowed: set[Role]) -> bool:
        return bool(self.roles.intersection(allowed))


class AclFilter(BaseModel):
    tenant_id: str
    allowed_source_ids: set[str] | None = None
    user_id: str
    roles: set[Role]

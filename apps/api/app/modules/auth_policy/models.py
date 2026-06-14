from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from app.modules.auth_policy.schemas import Role, TenantPolicy


@dataclass
class Tenant:
    id: str
    name: str
    status: str = "active"
    policy: TenantPolicy = field(default_factory=TenantPolicy)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class User:
    id: str
    external_subject: str
    email: str
    display_name: str
    status: str = "active"


@dataclass
class TenantMembership:
    tenant_id: str
    user_id: str
    role: Role
    status: str = "active"

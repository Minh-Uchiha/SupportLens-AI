from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class KnowledgeSource:
    id: str
    tenant_id: str
    type: str
    name: str
    connection_ref: str
    status: str = "enabled"
    sync_policy: str = "manual"
    permission_mode: str = "tenant"
    last_sync_at: datetime | None = None
    last_sync_status: str = "never_synced"
    last_failure_reason: str | None = None


@dataclass
class SourceDocument:
    id: str
    tenant_id: str
    source_id: str
    external_id: str
    title: str
    url: str
    version: str
    text: str
    freshness_status: str = "fresh"
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acl_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeChunk:
    id: str
    tenant_id: str
    source_id: str
    document_id: str
    chunk_index: int
    text: str
    citation_anchor: str
    acl_metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)


@dataclass
class IngestionJob:
    id: str
    tenant_id: str
    source_id: str
    job_type: str
    status: str = "queued"
    reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

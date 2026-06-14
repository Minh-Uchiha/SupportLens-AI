CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  retention_policy TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  external_subject TEXT NOT NULL,
  email TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  role TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (tenant_id, user_id, role)
);

CREATE TABLE IF NOT EXISTS tenant_policies (
  tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),
  citation_required BOOLEAN NOT NULL DEFAULT true,
  retention_settings JSONB NOT NULL DEFAULT '{}',
  logging_posture TEXT NOT NULL DEFAULT 'redacted'
);

CREATE TABLE IF NOT EXISTS knowledge_sources (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  sync_policy TEXT NOT NULL,
  permission_mode TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_documents (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES knowledge_sources(id),
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  version TEXT NOT NULL,
  freshness_status TEXT NOT NULL,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  document_id TEXT NOT NULL REFERENCES source_documents(id),
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  citation_anchor TEXT NOT NULL,
  acl_metadata JSONB NOT NULL DEFAULT '{}'
);

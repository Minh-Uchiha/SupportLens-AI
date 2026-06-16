from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_retrieval_indexes"
down_revision = "0001_initial_persistence"
branch_labels = None
depends_on = None

# The embedding dimension matches the default sentence-transformers model
# (all-MiniLM-L6-v2 produces 384-dim vectors). The deterministic fallback embedder
# uses the same dimension so the schema is identical regardless of which embedder ran.
EMBEDDING_DIM = 384


def upgrade() -> None:
    # Embedding provenance columns exist on every dialect so the re-embedding
    # workflow works the same on SQLite (tests) and Postgres (dev/prod).
    op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(), nullable=False, server_default=""))
    op.add_column("knowledge_chunks", sa.Column("embedding_version", sa.String(), nullable=False, server_default=""))

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite and other dialects rely on the JSON `embedding` column and the
        # Python retrieval fallback, so the native vector/FTS/trigram indexes are skipped.
        return

    # Native pgvector column powers cosine-distance similarity search on Postgres.
    op.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN embedding_vector vector({EMBEDDING_DIM})")
    op.execute("CREATE INDEX ix_knowledge_chunks_embedding_vector ON knowledge_chunks USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = 100)")

    # Generated tsvector keeps full-text rank queries simple and always in sync with `text`.
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED")
    op.execute("CREATE INDEX ix_knowledge_chunks_tsv ON knowledge_chunks USING gin (tsv)")

    # Trigram index supports fuzzy lexical matching (for example exact error codes with typos).
    op.execute("CREATE INDEX ix_knowledge_chunks_text_trgm ON knowledge_chunks USING gin (text gin_trgm_ops)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_text_trgm")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_tsv")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_vector")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS tsv")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding_vector")

    op.drop_column("knowledge_chunks", "embedding_version")
    op.drop_column("knowledge_chunks", "embedding_model")

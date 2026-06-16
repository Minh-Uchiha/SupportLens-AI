from __future__ import annotations

# Workers reuse the same connector registry as the API so source loading behaves
# identically whether ingestion runs inline or on a worker.
from app.modules.source_management.connectors import (
    LoadedDocument,
    load_documents_from_source,
    register_connector,
)

__all__ = ["LoadedDocument", "load_documents_from_source", "register_connector"]

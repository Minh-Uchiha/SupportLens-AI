from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 384 dims matches sentence-transformers/all-MiniLM-L6-v2. The deterministic
# fallback uses the same dimension so stored vectors and the pgvector column line
# up regardless of which embedder produced them.
EMBEDDING_DIM = 384

# Bump this when the embedding strategy changes in a way that requires re-embedding
# existing chunks. It is stored on every chunk so the re-embedding workflow can detect
# stale vectors by comparing model + version.
EMBEDDING_VERSION = "1"

# Marker model name used when sentence-transformers is unavailable. Storing this makes
# it obvious which chunks were embedded by the fallback so they can be re-embedded later.
_FALLBACK_MODEL = "deterministic-hash-fallback"


def current_embedding_model() -> str:
    """Return the embedding model identifier that the active embedder will report."""
    if _load_sentence_transformer() is not None:
        return get_settings().embedding_model
    return _FALLBACK_MODEL


def current_embedding_version() -> str:
    return EMBEDDING_VERSION


@lru_cache(maxsize=1)
def _load_sentence_transformer():
    """Load and cache the sentence-transformers model, or return None if unavailable.

    sentence-transformers (and torch) are heavy and optional, so tests and lightweight
    installs fall back to the deterministic embedder instead of failing.
    """
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:  # ImportError or transitive import failures (e.g. torch missing)
        logger.info("sentence-transformers not installed; using deterministic embedding fallback")
        return None
    try:
        model = SentenceTransformer(settings.embedding_model)
        logger.info("Loaded embedding model %s", settings.embedding_model)
        return model
    except Exception:
        # Model download/load failed; log with stack trace and degrade to the fallback
        # rather than blocking ingestion and retrieval entirely.
        logger.error("Failed to load embedding model %s; using fallback", settings.embedding_model, exc_info=True)
        return None


def _fallback_embedding(text: str) -> list[float]:
    """Hash tokens into a fixed-size vector so retrieval stays deterministic offline.

    This is not semantically meaningful, but it is stable for a given text, which keeps
    tests reproducible and lets the vector search path exercise real cosine math.
    """
    vector = [0.0] * EMBEDDING_DIM
    for token in text.lower().split():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def embed_texts(texts: list[str], embedding_options: dict | None = None) -> list[list[float]]:
    """Embed a batch of texts, preferring sentence-transformers and degrading safely."""
    if not texts:
        return []
    model = _load_sentence_transformer()
    if model is not None:
        try:
            logger.info("Embedding %d texts with %s", len(texts), get_settings().embedding_model)
            vectors = model.encode(texts, normalize_embeddings=True)
            return [list(map(float, vector)) for vector in vectors]
        except Exception:
            # Encoding failed at runtime; log and fall back so the caller still gets vectors.
            logger.error("Embedding encode failed; using deterministic fallback for %d texts", len(texts), exc_info=True)
    return [_fallback_embedding(text) for text in texts]

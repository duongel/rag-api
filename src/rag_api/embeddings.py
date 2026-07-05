"""Thin wrapper around the Ollama /api/embed endpoint.

Some embedding models require task-specific prefixes for good retrieval:
  - nomic-embed-text: ``search_document: <text>`` / ``search_query: <text>``
Most modern models (bge-m3, mxbai-embed-large) work best with no prefix.
The prefixes are selected automatically from the model name and can be
overridden via ``EMBED_DOC_PREFIX`` / ``EMBED_QUERY_PREFIX``.
"""

import logging

import requests

from .config import (
    OLLAMA_URL,
    EMBED_MODEL,
    EMBED_DOC_PREFIX,
    EMBED_QUERY_PREFIX,
)

logger = logging.getLogger(__name__)

# Models that need nomic-style task prefixes to retrieve well.
_NOMIC_DOC_PREFIX = "search_document: "
_NOMIC_QUERY_PREFIX = "search_query: "


def _resolve_prefix(configured: str, nomic_default: str) -> str:
    """Resolve an embedding prefix from config.

    ``auto`` applies the nomic prefix only for nomic-family models and no
    prefix otherwise. Any other value is used verbatim (empty string = none).
    """
    if configured != "auto":
        return configured
    return nomic_default if "nomic" in EMBED_MODEL.lower() else ""


_PREFIX_DOC = _resolve_prefix(EMBED_DOC_PREFIX, _NOMIC_DOC_PREFIX)
_PREFIX_QUERY = _resolve_prefix(EMBED_QUERY_PREFIX, _NOMIC_QUERY_PREFIX)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks (applies the document prefix if configured)."""
    return _embed([_PREFIX_DOC + t for t in texts])


def embed_query(text: str) -> list[float]:
    """Embed a search query (applies the query prefix if configured)."""
    return _embed([_PREFIX_QUERY + text])[0]


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=300,
    )
    if response.ok:
        return response.json()["embeddings"]

    # --- batch failed – fall back to one-by-one embedding -----------------
    error_body = response.text[:500] if response.text else "(empty)"
    logger.warning(
        "Batch embed failed (status %d, %d texts): %s – retrying individually",
        response.status_code,
        len(texts),
        error_body,
    )

    embeddings: list[list[float]] = []
    for i, text in enumerate(texts):
        single = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": [text]},
            timeout=300,
        )
        if single.ok:
            embeddings.extend(single.json()["embeddings"])
        else:
            # Individual text too large – log and raise so caller knows
            logger.error(
                "Embed failed for text %d/%d (len=%d): %s",
                i + 1,
                len(texts),
                len(text),
                single.text[:300],
            )
            single.raise_for_status()

    return embeddings



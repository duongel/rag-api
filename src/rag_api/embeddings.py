"""Thin wrapper around the Ollama /api/embed endpoint.

nomic-embed-text requires task-specific prefixes for good retrieval:
  - ``search_document: <text>`` when indexing documents
  - ``search_query: <text>``    when embedding a user query
"""

import logging

import requests

from .config import OLLAMA_URL, EMBED_MODEL

logger = logging.getLogger(__name__)

_PREFIX_DOC = "search_document: "
_PREFIX_QUERY = "search_query: "


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks (uses ``search_document:`` prefix)."""
    return _embed([_PREFIX_DOC + t for t in texts])


def embed_query(text: str) -> list[float]:
    """Embed a search query (uses ``search_query:`` prefix)."""
    return _embed([_PREFIX_QUERY + text])[0]


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["embeddings"]



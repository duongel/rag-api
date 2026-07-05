"""Optional cross-encoder reranking over HTTP.

When ``RERANK_ENABLED`` is set, search retrieves a larger candidate pool and
reorders it with a cross-encoder reranker served via the Hugging Face
text-embeddings-inference / Infinity ``POST /rerank`` API. A cross-encoder
scores each (query, document) pair jointly, which is substantially more
precise than the bi-encoder cosine similarity used for retrieval.

The integration is best-effort: if reranking is disabled, unconfigured, or the
reranker service is unreachable, the original result order is returned
unchanged so search never fails because of the reranker.
"""

import logging
from typing import Optional

import requests

from .config import (
    RERANK_ENABLED,
    RERANK_URL,
    RERANK_MODEL,
    RERANK_TIMEOUT_SECONDS,
    RERANK_DOC_CHARS,
)

logger = logging.getLogger(__name__)


def rerank_enabled() -> bool:
    """Return True when reranking is switched on and a URL is configured."""
    return bool(RERANK_ENABLED and RERANK_URL)


def _truncate(text: str) -> str:
    """Trim a candidate document to ``RERANK_DOC_CHARS`` (0 = no trimming)."""
    if RERANK_DOC_CHARS > 0:
        return text[:RERANK_DOC_CHARS]
    return text


def rerank_results(
    query: str,
    results: list[dict],
    top_k: int,
    *,
    content_key: str = "content",
) -> list[dict]:
    """Reorder *results* by cross-encoder relevance to *query*.

    Returns the top *top_k* results. On any failure (or when disabled) the
    input ordering is preserved and simply truncated to *top_k*.

    The reranker's normalized score is written to each returned result's
    ``rerank_score`` field for transparency; the original ``score`` is kept.
    """
    if not rerank_enabled() or not query or len(results) <= 1:
        return results[:top_k]

    documents = [_truncate(str(r.get(content_key, "") or "")) for r in results]
    scores = _request_scores(query, documents)
    if scores is None:
        return results[:top_k]

    ranked = sorted(
        zip(results, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )
    reranked: list[dict] = []
    for result, score in ranked[:top_k]:
        enriched = dict(result)
        enriched["rerank_score"] = round(float(score), 4)
        reranked.append(enriched)
    return reranked


def _request_scores(query: str, documents: list[str]) -> Optional[list[float]]:
    """Call the rerank endpoint and return one score per document.

    Returns None on any error so callers can fall back to the input order.
    """
    endpoint = f"{RERANK_URL.rstrip('/')}/rerank"
    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "texts": documents,
        "return_text": False,
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=RERANK_TIMEOUT_SECONDS)
        if not resp.ok:
            logger.warning("Reranker returned HTTP %d — keeping vector order", resp.status_code)
            return None
        data = resp.json()
    except Exception as exc:
        logger.warning("Reranker request failed (%s) — keeping vector order", exc)
        return None

    return _parse_scores(data, len(documents))


def _parse_scores(data: object, expected: int) -> Optional[list[float]]:
    """Extract index→score pairs from a TEI/Infinity rerank response.

    Both APIs return a list of ``{"index": i, "score": s}`` objects (TEI) or a
    ``{"results": [{"index": i, "relevance_score": s}, ...]}`` envelope
    (Infinity/cohere-style). Scores are mapped back to input order.
    """
    items = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(items, list) or len(items) != expected:
        logger.warning("Unexpected reranker response shape — keeping vector order")
        return None

    scores = [0.0] * expected
    for item in items:
        if not isinstance(item, dict) or "index" not in item:
            return None
        idx = item["index"]
        if not isinstance(idx, int) or not (0 <= idx < expected):
            return None
        score = item.get("score", item.get("relevance_score"))
        if score is None:
            return None
        scores[idx] = float(score)
    return scores

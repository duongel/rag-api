"""Tests for the embedding-model upgrade: prefix selection and reranking."""

import importlib
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Model-aware embedding prefixes
# ---------------------------------------------------------------------------


def _reload_embeddings(monkeypatch, **env):
    """Reload rag_api.embeddings with patched config env values."""
    import rag_api.config as config
    import rag_api.embeddings as embeddings

    for key, value in env.items():
        monkeypatch.setattr(config, key, value, raising=False)
    # embeddings binds config values at import time
    importlib.reload(embeddings)
    return embeddings


class TestEmbeddingPrefixes:
    def test_nomic_model_uses_search_prefixes(self, monkeypatch):
        emb = _reload_embeddings(
            monkeypatch,
            EMBED_MODEL="nomic-embed-text",
            EMBED_DOC_PREFIX="auto",
            EMBED_QUERY_PREFIX="auto",
        )
        assert emb._PREFIX_DOC == "search_document: "
        assert emb._PREFIX_QUERY == "search_query: "

    def test_bge_model_uses_no_prefix(self, monkeypatch):
        emb = _reload_embeddings(
            monkeypatch,
            EMBED_MODEL="bge-m3",
            EMBED_DOC_PREFIX="auto",
            EMBED_QUERY_PREFIX="auto",
        )
        assert emb._PREFIX_DOC == ""
        assert emb._PREFIX_QUERY == ""

    def test_explicit_prefix_overrides_auto(self, monkeypatch):
        emb = _reload_embeddings(
            monkeypatch,
            EMBED_MODEL="bge-m3",
            EMBED_DOC_PREFIX="passage: ",
            EMBED_QUERY_PREFIX="query: ",
        )
        assert emb._PREFIX_DOC == "passage: "
        assert emb._PREFIX_QUERY == "query: "

    @classmethod
    def teardown_class(cls):
        # Restore module to its configured default state for other tests.
        import rag_api.embeddings as embeddings
        importlib.reload(embeddings)


# ---------------------------------------------------------------------------
# Reranker HTTP client
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, ok=True, status_code=200):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class TestReranker:
    def _results(self):
        return [
            {"file_path": "a", "content": "alpha", "score": 0.9},
            {"file_path": "b", "content": "beta", "score": 0.8},
            {"file_path": "c", "content": "gamma", "score": 0.7},
        ]

    def test_disabled_returns_input_truncated(self):
        from rag_api import reranker

        with patch.object(reranker, "RERANK_ENABLED", False):
            out = reranker.rerank_results("q", self._results(), top_k=2)
        assert [r["file_path"] for r in out] == ["a", "b"]
        assert "rerank_score" not in out[0]

    def test_active_reorders_by_rerank_score(self):
        from rag_api import reranker

        # Reranker says 'c' is most relevant, then 'a', then 'b'
        payload = [
            {"index": 0, "score": 0.2},
            {"index": 1, "score": 0.1},
            {"index": 2, "score": 0.99},
        ]
        with patch.object(reranker, "RERANK_ENABLED", True), \
             patch.object(reranker, "RERANK_URL", "http://reranker:80"), \
             patch.object(reranker.requests, "post", return_value=_FakeResponse(payload)):
            out = reranker.rerank_results("q", self._results(), top_k=2)

        assert [r["file_path"] for r in out] == ["c", "a"]
        assert out[0]["rerank_score"] == 0.99

    def test_infinity_style_envelope_is_parsed(self):
        from rag_api import reranker

        payload = {"results": [
            {"index": 0, "relevance_score": 0.1},
            {"index": 1, "relevance_score": 0.5},
            {"index": 2, "relevance_score": 0.2},
        ]}
        with patch.object(reranker, "RERANK_ENABLED", True), \
             patch.object(reranker, "RERANK_URL", "http://reranker:80"), \
             patch.object(reranker.requests, "post", return_value=_FakeResponse(payload)):
            out = reranker.rerank_results("q", self._results(), top_k=3)

        assert [r["file_path"] for r in out] == ["b", "c", "a"]

    def test_unreachable_reranker_falls_back_to_input_order(self):
        from rag_api import reranker

        with patch.object(reranker, "RERANK_ENABLED", True), \
             patch.object(reranker, "RERANK_URL", "http://reranker:80"), \
             patch.object(reranker.requests, "post", side_effect=Exception("boom")):
            out = reranker.rerank_results("q", self._results(), top_k=2)

        assert [r["file_path"] for r in out] == ["a", "b"]

    def test_malformed_response_falls_back(self):
        from rag_api import reranker

        with patch.object(reranker, "RERANK_ENABLED", True), \
             patch.object(reranker, "RERANK_URL", "http://reranker:80"), \
             patch.object(reranker.requests, "post", return_value=_FakeResponse([{"nope": 1}])):
            out = reranker.rerank_results("q", self._results(), top_k=3)

        assert [r["file_path"] for r in out] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Search integration
# ---------------------------------------------------------------------------


class TestSearchRerankIntegration:
    def _make_searcher(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 100
        mock_collection.query.return_value = {
            "ids": [["id1", "id2", "id3"]],
            "documents": [["doc one", "doc two", "doc three"]],
            "metadatas": [[
                {"file_path": "one.pdf", "source": "paperless"},
                {"file_path": "two.pdf", "source": "paperless"},
                {"file_path": "three.pdf", "source": "paperless"},
            ]],
            "distances": [[0.1, 0.2, 0.3]],
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection
        return searcher

    def test_semantic_search_applies_rerank_when_enabled(self):
        from rag_api import search

        searcher = self._make_searcher()

        def fake_rerank(query, results, top_k, **kwargs):
            # Reverse the vector order to prove reranking took effect.
            return list(reversed(results))[:top_k]

        with patch("rag_api.search.embed_query", return_value=[0.1] * 8), \
             patch("rag_api.search.rerank_enabled", return_value=True), \
             patch("rag_api.search.rerank_results", side_effect=fake_rerank):
            results = searcher.semantic_search("test", top_k=2, expand_links=False)

        assert [r["file_path"] for r in results] == ["three.pdf", "two.pdf"]

    def test_semantic_search_skips_rerank_for_date_sorted(self):
        from rag_api import search

        searcher = self._make_searcher()

        with patch("rag_api.search.embed_query", return_value=[0.1] * 8), \
             patch("rag_api.search.rerank_enabled", return_value=True), \
             patch("rag_api.search.rerank_results") as mock_rerank:
            searcher.semantic_search("test", top_k=2, sort_by_date=True, expand_links=False)

        mock_rerank.assert_not_called()

    def test_semantic_search_no_rerank_when_disabled(self):
        searcher = self._make_searcher()

        with patch("rag_api.search.embed_query", return_value=[0.1] * 8), \
             patch("rag_api.search.rerank_enabled", return_value=False), \
             patch("rag_api.search.rerank_results") as mock_rerank:
            results = searcher.semantic_search("test", top_k=2, expand_links=False)

        mock_rerank.assert_not_called()
        assert [r["file_path"] for r in results] == ["one.pdf", "two.pdf"]

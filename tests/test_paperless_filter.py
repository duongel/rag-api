"""Tests for Paperless pre-filter search functionality."""

from unittest.mock import MagicMock, patch
import os

import pytest

os.environ.setdefault("CHROMA_PATH", "/tmp/test_chroma")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("PAPERLESS_URL", "http://paperless:8000")
os.environ.setdefault("PAPERLESS_TOKEN", "test-token")


# ---------------------------------------------------------------------------
# query_paperless_doc_ids
# ---------------------------------------------------------------------------


class TestQueryPaperlessDocIds:
    def test_returns_none_when_no_filters(self):
        from rag_api.search import query_paperless_doc_ids

        assert query_paperless_doc_ids() is None

    def test_returns_none_when_no_paperless_config(self):
        from rag_api.search import query_paperless_doc_ids

        with patch("rag_api.config.PAPERLESS_URL", ""), patch("rag_api.config.PAPERLESS_TOKEN", ""):
            result = query_paperless_doc_ids(tags=["etron"])
        assert result is None

    def test_returns_doc_ids_for_tag_filter(self):
        from rag_api.search import query_paperless_doc_ids

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "results": [{"id": 42}, {"id": 55}]
        }

        with patch("requests.get", return_value=mock_resp) as mocked:
            result = query_paperless_doc_ids(tags=["etron"])

        assert result == ["42", "55"]
        call_kwargs = mocked.call_args
        assert "tags__name__icontains" in call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))

    def test_returns_empty_list_when_no_matches(self):
        from rag_api.search import query_paperless_doc_ids

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"results": []}

        with patch("requests.get", return_value=mock_resp):
            result = query_paperless_doc_ids(tags=["nonexistent"])

        assert result == []

    def test_returns_none_on_api_failure(self):
        from rag_api.search import query_paperless_doc_ids

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500

        with patch("requests.get", return_value=mock_resp):
            result = query_paperless_doc_ids(tags=["etron"])

        assert result is None

    def test_passes_year_and_correspondent(self):
        from rag_api.search import query_paperless_doc_ids

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"results": [{"id": 10}]}

        with patch("requests.get", return_value=mock_resp) as mocked:
            result = query_paperless_doc_ids(
                correspondent="Audi", created_year=2025
            )

        assert result == ["10"]
        params = mocked.call_args.kwargs.get("params", mocked.call_args[1].get("params", {}))
        assert params["correspondent__name__icontains"] == "Audi"
        assert params["created__year"] == 2025


# ---------------------------------------------------------------------------
# Semantic search with pre-filter
# ---------------------------------------------------------------------------

EMBED_DIM = 8


def _fake_embed(texts):
    return [[float(i)] * EMBED_DIM for i in range(len(texts))]


def _fake_embed_query(text):
    return [0.5] * EMBED_DIM


@pytest.fixture()
def searcher():
    """Create a Searcher with an in-memory ChromaDB and two indexed docs."""
    import chromadb

    ephemeral = chromadb.EphemeralClient()

    with (
        patch("rag_api.indexer.embed_documents", side_effect=_fake_embed),
        patch("rag_api.indexer.chromadb.PersistentClient", return_value=ephemeral),
    ):
        from rag_api.indexer import Indexer
        from rag_api.search import Searcher

        idx = Indexer()

        # Index two paperless docs
        idx.index_paperless_doc({
            "id": 42,
            "content": "Audi e-tron Rechnung über 500 EUR",
            "title": "Audi Rechnung",
            "tags": [1],
        })
        idx.index_paperless_doc({
            "id": 55,
            "content": "BMW Werkstattrechnung über 300 EUR",
            "title": "BMW Rechnung",
            "tags": [2],
        })

        with patch("rag_api.search.embed_query", side_effect=_fake_embed_query):
            yield Searcher(idx)


class TestSemanticSearchWithFilter:
    def test_no_filter_returns_both(self, searcher):
        results = searcher.semantic_search("Rechnung", top_k=10, expand_links=False)
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert "42" in doc_ids or "55" in doc_ids

    def test_filter_restricts_to_matching_docs(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_doc_ids=["42"],
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"42"}

    def test_empty_filter_returns_nothing(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_doc_ids=[],
        )
        assert results == []


class TestKeywordSearchWithFilter:
    def test_filter_restricts_keyword_results(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_doc_ids=["42"],
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        # Should only contain doc 42, not 55
        assert "55" not in doc_ids

    def test_empty_filter_returns_nothing(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_doc_ids=[],
        )
        assert results == []

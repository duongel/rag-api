"""Tests for Paperless ChromaDB-native filter search functionality."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _build_chromadb_filters
# ---------------------------------------------------------------------------


class TestBuildChromadbFilters:
    def test_returns_none_when_no_filters(self):
        from rag_api.search import _build_chromadb_filters

        assert _build_chromadb_filters() is None

    def test_single_tag_filter(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron"])
        assert result == {"$and": [{"source": "paperless"}, {"ptag_etron": 1}]}

    def test_multiple_tags_filter(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron", "rechnung"])
        assert result == {
            "$and": [
                {"source": "paperless"},
                {"ptag_etron": 1},
                {"ptag_rechnung": 1},
            ]
        }

    def test_year_filter(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(created_year=2025)
        assert result == {"$and": [{"source": "paperless"}, {"created_year": 2025}]}

    def test_correspondent_filter_lowercased(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(correspondent="Audi")
        assert result == {"$and": [{"source": "paperless"}, {"correspondent_name": "audi"}]}

    def test_combined_filters(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(
            tags=["etron"], correspondent="Audi", created_year=2025
        )
        assert result == {
            "$and": [
                {"source": "paperless"},
                {"created_year": 2025},
                {"correspondent_name": "audi"},
                {"ptag_etron": 1},
            ]
        }


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
    """Create a Searcher with an in-memory ChromaDB and two indexed docs with metadata."""
    import chromadb

    ephemeral = chromadb.EphemeralClient()

    with (
        patch("rag_api.indexer.embed_documents", side_effect=_fake_embed),
        patch("rag_api.indexer.chromadb.PersistentClient", return_value=ephemeral),
    ):
        from rag_api.indexer import Indexer
        from rag_api.search import Searcher

        idx = Indexer()

        # Index two paperless docs with full metadata
        idx.index_paperless_doc({
            "id": 42,
            "content": "Audi e-tron Rechnung über 500 EUR",
            "title": "Audi Rechnung",
            "tags": [1],
            "created": "2025-03-15T00:00:00Z",
        })
        idx.index_paperless_doc({
            "id": 55,
            "content": "BMW Werkstattrechnung über 300 EUR",
            "title": "BMW Rechnung",
            "tags": [2],
            "created": "2024-06-01T00:00:00Z",
        })

        with patch("rag_api.search.embed_query", side_effect=_fake_embed_query):
            yield Searcher(idx)


class TestSemanticSearchWithFilter:
    def test_no_filter_returns_both(self, searcher):
        results = searcher.semantic_search("Rechnung", top_k=10, expand_links=False)
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert "42" in doc_ids or "55" in doc_ids

    def test_year_filter_restricts_results(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_created_year=2025,
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"42"}

    def test_year_filter_no_match_returns_empty(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_created_year=2020,
        )
        assert results == []


class TestKeywordSearchWithFilter:
    def test_year_filter_restricts_keyword_results(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_created_year=2025,
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        # Should only contain doc 42 (2025), not 55 (2024)
        assert "55" not in doc_ids

    def test_year_filter_no_match_returns_empty(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_created_year=2020,
        )
        assert results == []

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
        assert result == {"source": "paperless"}

    def test_multiple_tags_filter(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron", "rechnung"])
        assert result == {"source": "paperless"}

    def test_year_filter(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(created_year=2025)
        assert result == {"$and": [{"source": "paperless"}, {"created_year": 2025}]}

    def test_correspondent_filter_lowercased(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(correspondent="Audi")
        assert result == {"source": "paperless"}

    def test_combined_filters(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(
            tags=["etron"], correspondent="Audi", created_year=2025
        )
        assert result == {
            "$and": [
                {"source": "paperless"},
                {"created_year": 2025},
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

    def test_filename_matching_stays_enabled_with_paperless_filters(self, searcher):
        searcher.indexer.collection.upsert(
            ids=["paperless::invoices/INV-1234.pdf#chunk_0"],
            embeddings=[_fake_embed_query("x")],
            documents=["OCR without invoice id"],
            metadatas=[{
                "file_path": "invoices/INV-1234.pdf",
                "section": "",
                "file_hash": "x",
                "chunk_index": 0,
                "source": "paperless",
                "paperless_doc_id": "999",
                "correspondent_name": "audi ag",
                "tag_names": "car",
                "created_year": 2025,
            }],
        )
        searcher.indexer._file_sources["paperless::invoices/INV-1234.pdf"] = "paperless"

        results = searcher.keyword_search(
            "inv-1234",
            top_k=10,
            paperless_correspondent="Audi",
        )

        assert any(r["match_type"] == "filename" for r in results)

    def test_text_filters_use_case_insensitive_substring(self, searcher):
        searcher.indexer.collection.upsert(
            ids=["paperless::docs/partial.pdf#chunk_0"],
            embeddings=[_fake_embed_query("x")],
            documents=["generic content"],
            metadatas=[{
                "file_path": "docs/partial.pdf",
                "section": "",
                "file_hash": "y",
                "chunk_index": 0,
                "source": "paperless",
                "paperless_doc_id": "1000",
                "correspondent_name": "audi ag",
                "tag_names": "e-tron,leasing",
                "created_year": 2025,
            }],
        )

        results = searcher.keyword_search(
            "generic",
            top_k=10,
            paperless_correspondent="AUDI",
            paperless_tags=["tron"],
        )

        assert any(r.get("paperless_doc_id") == "1000" for r in results)

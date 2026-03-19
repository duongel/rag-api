"""Tests for Paperless ChromaDB-native filter search functionality."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _build_chromadb_filters — Paperless API pre-filter path
# ---------------------------------------------------------------------------


class TestBuildChromadbFilters:
    """Test _build_chromadb_filters with both Paperless API and fallback paths."""

    def test_returns_none_when_no_filters(self):
        from rag_api.search import _build_chromadb_filters

        assert _build_chromadb_filters() is None

    # -- Paperless API pre-filter path --

    @patch("rag_api.search._query_paperless_api", return_value=["42", "100", "200"])
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_tag_multiple_results(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron"])
        mock_query.assert_called_once_with(
            tags=["etron"], correspondent=None, created_year=None, document_type=None,
            max_ids=200,
        )
        assert result == {"$or": [
            {"paperless_doc_id": "42"},
            {"paperless_doc_id": "100"},
            {"paperless_doc_id": "200"},
        ]}

    @patch("rag_api.search._query_paperless_api", return_value=["42"])
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_single_result_returns_direct_filter(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron"])
        assert result == {"paperless_doc_id": "42"}

    @patch("rag_api.search._query_paperless_api", return_value=[])
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_no_matches_returns_no_match(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["unknown"])
        assert result == {"paperless_doc_id": "__NO_MATCH__"}

    @patch("rag_api.search._query_paperless_api", return_value=["10", "20"])
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_combined_filters(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(
            tags=["etron"], correspondent="Audi", created_year=2025,
        )
        mock_query.assert_called_once_with(
            tags=["etron"], correspondent="Audi", created_year=2025, document_type=None,
            max_ids=200,
        )
        assert result == {"$or": [
            {"paperless_doc_id": "10"},
            {"paperless_doc_id": "20"},
        ]}

    @patch("rag_api.search._query_paperless_api", return_value=["42", "55"])
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_document_type_filter(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(document_type="Rechnung")
        mock_query.assert_called_once_with(
            tags=None, correspondent=None, created_year=None, document_type="Rechnung",
            max_ids=200,
        )
        assert result == {"$or": [
            {"paperless_doc_id": "42"},
            {"paperless_doc_id": "55"},
        ]}

    # -- API failure → legacy fallback --

    @patch("rag_api.search._query_paperless_api", return_value=None)
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_api_failure_falls_back_to_legacy(self, mock_query):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron"])
        assert result == {"$and": [{"source": "paperless"}, {"ptag_etron": 1}]}

    # -- Legacy path (no Paperless credentials) --

    @patch("rag_api.search.PAPERLESS_TOKEN", "")
    @patch("rag_api.search.PAPERLESS_URL", "")
    def test_fallback_single_tag(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron"])
        assert result == {"$and": [{"source": "paperless"}, {"ptag_etron": 1}]}

    @patch("rag_api.search.PAPERLESS_TOKEN", "")
    @patch("rag_api.search.PAPERLESS_URL", "")
    def test_fallback_multiple_tags(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(tags=["etron", "rechnung"])
        assert result == {
            "$and": [
                {"source": "paperless"},
                {"ptag_etron": 1},
                {"ptag_rechnung": 1},
            ]
        }

    @patch("rag_api.search.PAPERLESS_TOKEN", "")
    @patch("rag_api.search.PAPERLESS_URL", "")
    def test_fallback_year(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(created_year=2025)
        assert result == {"$and": [{"source": "paperless"}, {"created_year": 2025}]}

    @patch("rag_api.search.PAPERLESS_TOKEN", "")
    @patch("rag_api.search.PAPERLESS_URL", "")
    def test_fallback_correspondent(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(correspondent="Audi")
        assert result == {"$and": [{"source": "paperless"}, {"correspondent_name_lc": "audi"}]}

    @patch("rag_api.search.PAPERLESS_TOKEN", "")
    @patch("rag_api.search.PAPERLESS_URL", "")
    def test_fallback_combined(self):
        from rag_api.search import _build_chromadb_filters

        result = _build_chromadb_filters(
            tags=["etron"], correspondent="Audi", created_year=2025
        )
        assert result == {
            "$and": [
                {"source": "paperless"},
                {"created_year": 2025},
                {"correspondent_name_lc": "audi"},
                {"ptag_etron": 1},
            ]
        }


class TestPaperlessLookupPagination:
    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_document_type_lookup_follows_next_page(self):
        from rag_api.search import _DOCTYPE_NAME_TO_ID, _ensure_paperless_lookups

        _DOCTYPE_NAME_TO_ID.clear()

        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.ok = True
            if url == "https://example.com/api/tags/":
                resp.json.return_value = {"results": [], "next": None}
            elif url == "https://example.com/api/correspondents/":
                resp.json.return_value = {"results": [], "next": None}
            elif url == "https://example.com/api/document_types/":
                resp.json.return_value = {
                    "results": [{"id": 1, "name": "Invoice"}],
                    "next": "https://example.com/api/document_types/?page=2",
                }
            elif url == "https://example.com/api/document_types/?page=2":
                resp.json.return_value = {
                    "results": [{"id": 2, "name": "Contract"}],
                    "next": None,
                }
            else:
                resp.ok = False
                resp.json.return_value = {}
            return resp

        with patch("requests.get", side_effect=fake_get):
            _ensure_paperless_lookups(need_doctypes=True)

        assert _DOCTYPE_NAME_TO_ID["invoice"] == 1
        assert _DOCTYPE_NAME_TO_ID["contract"] == 2

    @patch("rag_api.search.PAPERLESS_TOKEN", "test-token")
    @patch("rag_api.search.PAPERLESS_URL", "https://example.com")
    def test_query_refreshes_lookup_caches_before_returning_unknown(self):
        from rag_api.search import (
            _CORR_NAME_TO_ID,
            _DOCTYPE_NAME_TO_ID,
            _TAG_NAME_TO_ID,
            _query_paperless_api,
        )

        _TAG_NAME_TO_ID.clear()
        _DOCTYPE_NAME_TO_ID.clear()
        _CORR_NAME_TO_ID.clear()

        calls = {"tags": 0, "doctypes": 0, "corrs": 0}

        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.ok = True
            if url == "https://example.com/api/tags/":
                calls["tags"] += 1
                if calls["tags"] == 1:
                    resp.json.return_value = {"results": [{"id": 1, "name": "oldtag"}], "next": None}
                else:
                    resp.json.return_value = {"results": [{"id": 2, "name": "newtag"}], "next": None}
            elif url == "https://example.com/api/document_types/":
                calls["doctypes"] += 1
                if calls["doctypes"] == 1:
                    resp.json.return_value = {"results": [{"id": 10, "name": "oldtype"}], "next": None}
                else:
                    resp.json.return_value = {"results": [{"id": 11, "name": "newtype"}], "next": None}
            elif url == "https://example.com/api/correspondents/":
                calls["corrs"] += 1
                if calls["corrs"] == 1:
                    resp.json.return_value = {"results": [{"id": 20, "name": "oldcorr"}], "next": None}
                else:
                    resp.json.return_value = {"results": [{"id": 21, "name": "newcorr"}], "next": None}
            elif url == "https://example.com/api/documents/":
                resp.json.return_value = {"results": [{"id": 42}], "next": None}
            else:
                resp.ok = False
                resp.json.return_value = {}
            return resp

        with patch("requests.get", side_effect=fake_get):
            _query_paperless_api(tags=["oldtag"], correspondent="oldcorr", document_type="oldtype")
            result = _query_paperless_api(
                tags=["newtag"],
                correspondent="newcorr",
                document_type="newtype",
            )

        assert result == ["42"]
        assert calls["tags"] >= 2
        assert calls["doctypes"] >= 2
        assert calls["corrs"] >= 2


# ---------------------------------------------------------------------------
# Semantic search with pre-filter
# ---------------------------------------------------------------------------

EMBED_DIM = 8


def _fake_embed(texts):
    return [[float(i)] * EMBED_DIM for i in range(len(texts))]


def _fake_embed_query(text):
    return [0.5] * EMBED_DIM


def _fake_paperless_api(url, **kwargs):
    """Mock Paperless API responses for tags and correspondents."""
    resp = MagicMock()
    resp.ok = True
    if "/api/tags/" in url and "?" not in url.split("/api/tags/")[1].rstrip("/"):
        # Individual tag lookup: /api/tags/<id>/
        tag_id = url.rstrip("/").split("/")[-1]
        names = {"1": "etron", "2": "werkstatt", "3": "versicherung"}
        resp.json.return_value = {"id": int(tag_id), "name": names.get(tag_id, f"tag{tag_id}")}
    elif "/api/tags/" in url:
        # Batch tag lookup: /api/tags/?id__in=...
        id_in = kwargs.get("params", {}).get("id__in", "")
        ids = id_in.split(",") if id_in else []
        names = {"1": "etron", "2": "werkstatt", "3": "versicherung"}
        resp.json.return_value = {"results": [{"id": int(i), "name": names.get(i, f"tag{i}")} for i in ids if i in names]}
    elif "/api/correspondents/" in url:
        corr_id = url.rstrip("/").split("/")[-1]
        names = {"10": "Audi AG", "20": "BMW Group"}
        resp.json.return_value = {"id": int(corr_id), "name": names.get(corr_id, f"corr{corr_id}")}
    else:
        resp.ok = False
    return resp


@pytest.fixture()
def searcher():
    """Create a Searcher with an in-memory ChromaDB and two indexed docs with metadata.

    Patches PAPERLESS_URL/TOKEN to empty so _build_chromadb_filters uses
    the legacy ChromaDB metadata fallback path (matching the metadata set
    up in this fixture).
    """
    import chromadb

    ephemeral = chromadb.EphemeralClient()
    # Ensure a clean collection even if a previous test leaked data
    try:
        ephemeral.delete_collection("rag_documents")
    except Exception:
        pass

    with (
        patch("rag_api.indexer.embed_documents", side_effect=_fake_embed),
        patch("rag_api.indexer.chromadb.PersistentClient", return_value=ephemeral),
        patch("requests.get", side_effect=_fake_paperless_api),
        patch("rag_api.search.PAPERLESS_URL", ""),
        patch("rag_api.search.PAPERLESS_TOKEN", ""),
    ):
        from rag_api.indexer import Indexer, _PAPERLESS_TAG_NAME_CACHE, _PAPERLESS_CORRESPONDENT_CACHE
        from rag_api.search import Searcher

        _PAPERLESS_TAG_NAME_CACHE.clear()
        _PAPERLESS_CORRESPONDENT_CACHE.clear()

        idx = Indexer()

        # Index two paperless docs with full metadata
        idx.index_paperless_doc({
            "id": 42,
            "content": "Audi e-tron Rechnung über 500 EUR",
            "title": "Audi Rechnung",
            "tags": [1],
            "correspondent": 10,
            "created": "2025-03-15T00:00:00Z",
        })
        idx.index_paperless_doc({
            "id": 55,
            "content": "BMW Werkstattrechnung über 300 EUR",
            "title": "BMW Rechnung",
            "tags": [2],
            "correspondent": 20,
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

    def test_tag_filter_restricts_results(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_tags=["etron"],
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"42"}

    def test_correspondent_filter_restricts_results(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_correspondent="BMW Group",
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"55"}

    def test_combined_tag_and_year_filter(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_tags=["etron"], paperless_created_year=2025,
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"42"}

    def test_year_filter_no_match_returns_empty(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_created_year=2020,
        )
        assert results == []

    def test_tag_filter_no_match_returns_empty(self, searcher):
        results = searcher.semantic_search(
            "Rechnung", top_k=10, expand_links=False,
            paperless_tags=["nonexistent"],
        )
        assert results == []


class TestKeywordSearchWithFilter:
    def test_year_filter_restricts_keyword_results(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_created_year=2025,
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert "55" not in doc_ids

    def test_tag_filter_restricts_keyword_results(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_tags=["werkstatt"],
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
        assert doc_ids == {"55"}

    def test_correspondent_filter_restricts_keyword_results(self, searcher):
        results = searcher.keyword_search(
            "Rechnung", top_k=10,
            paperless_correspondent="Audi AG",
        )
        doc_ids = {r.get("paperless_doc_id") for r in results}
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
                "correspondent_name": "Audi AG",
                "correspondent_name_lc": "audi ag",
                "created_year": 2025,
            }],
        )
        searcher.indexer._file_sources["paperless::invoices/INV-1234.pdf"] = "paperless"

        results = searcher.keyword_search(
            "inv-1234",
            top_k=10,
            paperless_correspondent="Audi AG",
        )

        assert any(r["match_type"] == "filename" for r in results)

    def test_exact_tag_and_correspondent_filtering(self, searcher):
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
                "correspondent_name": "Audi AG",
                "correspondent_name_lc": "audi ag",
                "ptag_e-tron": 1,
                "ptag_leasing": 1,
                "created_year": 2025,
            }],
        )

        results = searcher.keyword_search(
            "generic",
            top_k=10,
            paperless_correspondent="Audi AG",
            paperless_tags=["e-tron"],
        )

        assert any(r.get("paperless_doc_id") == "1000" for r in results)

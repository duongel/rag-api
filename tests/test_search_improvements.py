"""Tests for search improvements: multi-word keyword AND logic, hybrid search, date sorting."""

import re
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Multi-word keyword scoring
# ---------------------------------------------------------------------------


class TestKeywordScoreMulti:
    def test_basic_two_term_score(self):
        from rag_api.search import Searcher

        doc = "Der Kaufvertrag für das Grundstück in Montabaur wurde am 01.01.2020 geschlossen."
        terms = ["kaufvertrag", "grundstück"]
        patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms
        ]
        score = Searcher._keyword_score_multi(doc, terms, patterns)
        assert score >= 0.70
        # Both terms are present and within 200 chars -> proximity bonus
        assert score >= 0.80

    def test_proximity_bonus_when_terms_close(self):
        from rag_api.search import Searcher

        doc = "Kaufvertrag Grundstück"
        terms = ["kaufvertrag", "grundstück"]
        patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms
        ]
        score = Searcher._keyword_score_multi(doc, terms, patterns)
        # Very close terms -> should get proximity bonus
        assert score >= 0.80

    def test_no_proximity_bonus_when_terms_far_apart(self):
        from rag_api.search import Searcher

        # Ensure terms are more than 200 chars apart
        doc = "Kaufvertrag" + " x" * 150 + " Grundstück"
        terms = ["kaufvertrag", "grundstück"]
        patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms
        ]
        score = Searcher._keyword_score_multi(doc, terms, patterns)
        # No proximity bonus but still a valid match
        assert 0.70 <= score < 0.80

    def test_single_term_still_works(self):
        """Edge case: _keyword_score_multi with a single term."""
        from rag_api.search import Searcher

        doc = "Der Kaufvertrag"
        terms = ["kaufvertrag"]
        patterns = [re.compile(r"\b" + re.escape("kaufvertrag") + r"\b", re.IGNORECASE)]
        score = Searcher._keyword_score_multi(doc, terms, patterns)
        assert score >= 0.70


# ---------------------------------------------------------------------------
# Multi-word keyword search AND logic
# ---------------------------------------------------------------------------


class TestMultiWordKeywordSearch:
    """Test that keyword_search splits multi-word queries with AND logic."""

    def _make_searcher(self, docs, metadatas):
        """Build a Searcher with a mocked indexer and ChromaDB collection."""
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer._file_sources = {}
        mock_indexer._file_path_from_key = lambda k: k.split("::", 1)[1]

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": docs,
            "metadatas": metadatas,
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection
        return searcher

    def test_multiword_matches_both_terms(self):
        docs = [
            "Der Kaufvertrag für das Grundstück in Montabaur",
            "Grundsteuer Bescheid Montabaur",
            "Kaufvertrag Audi e-tron",
        ]
        metas = [
            {"file_path": "a.md", "section": "", "source": "paperless"},
            {"file_path": "b.md", "section": "", "source": "paperless"},
            {"file_path": "c.md", "section": "", "source": "paperless"},
        ]
        searcher = self._make_searcher(docs, metas)
        results = searcher.keyword_search("kaufvertrag grundstück", top_k=5)

        # Only doc a.md contains both "kaufvertrag" and "grundstück"
        assert len(results) == 1
        assert results[0]["file_path"] == "a.md"

    def test_single_word_still_works_as_substring(self):
        docs = [
            "Der NanoHD Access Point ist schnell",
            "Kein Match hier",
        ]
        metas = [
            {"file_path": "ap.md", "section": "", "source": "obsidian"},
            {"file_path": "other.md", "section": "", "source": "obsidian"},
        ]
        searcher = self._make_searcher(docs, metas)
        results = searcher.keyword_search("NanoHD", top_k=5)

        assert len(results) == 1
        assert results[0]["file_path"] == "ap.md"

    def test_filename_and_content_match_do_not_duplicate_paperless_result(self):
        docs = ["invoice details and amount"]
        metas = [
            {"file_path": "invoice.pdf", "section": "", "source": "paperless"},
        ]
        searcher = self._make_searcher(docs, metas)
        searcher.indexer._file_sources = {"paperless::invoice.pdf": "paperless"}

        results = searcher.keyword_search("invoice", top_k=5)

        assert len(results) == 1
        assert results[0]["file_path"] == "invoice.pdf"
        assert results[0]["match_type"] == "filename"


# ---------------------------------------------------------------------------
# Date sorting
# ---------------------------------------------------------------------------


class TestDateSorting:
    def test_semantic_search_dedups_multiple_chunks_from_same_doc(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.query.return_value = {
            "ids": [["id1", "id2", "id3"]],
            "documents": [["best chunk", "weaker chunk", "other doc"]],
            "metadatas": [[
                {"file_path": "same.pdf", "section": "42", "source": "paperless"},
                {"file_path": "same.pdf", "section": "42", "source": "paperless"},
                {"file_path": "other.pdf", "section": "43", "source": "paperless"},
            ]],
            "distances": [[0.1, 0.2, 0.3]],
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        with patch("rag_api.search.embed_query", return_value=[0.1] * 768):
            results = searcher.semantic_search("test", top_k=5, expand_links=False)

        assert [r["file_path"] for r in results] == ["same.pdf", "other.pdf"]
        assert results[0]["content"] == "best chunk"

    def test_sort_by_date_fetches_wider_candidate_pool_without_filter(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 1000
        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        with patch("rag_api.search.embed_query", return_value=[0.1] * 768):
            searcher.semantic_search("test", top_k=5, sort_by_date=True, expand_links=False)

        assert mock_collection.query.call_args.kwargs["n_results"] == 200

    def test_sort_by_date_reorders_results(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 3

        # Simulate chromadb query returning 3 results with different dates
        mock_collection.query.return_value = {
            "ids": [["id1", "id2", "id3"]],
            "documents": [["old doc", "newest doc", "middle doc"]],
            "metadatas": [[
                {"file_path": "old.pdf", "source": "paperless", "created": "2024-01-15"},
                {"file_path": "new.pdf", "source": "paperless", "created": "2025-11-01"},
                {"file_path": "mid.pdf", "source": "paperless", "created": "2025-06-15"},
            ]],
            "distances": [[0.3, 0.25, 0.28]],  # new.pdf has best score too
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        with patch("rag_api.search.embed_query", return_value=[0.1] * 768):
            results = searcher.semantic_search("test", top_k=5, sort_by_date=True, expand_links=False)

        assert len(results) == 3
        # Should be sorted newest first
        assert results[0]["file_path"] == "new.pdf"
        assert results[1]["file_path"] == "mid.pdf"
        assert results[2]["file_path"] == "old.pdf"

    def test_sort_by_date_false_keeps_score_order(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 2

        # ChromaDB returns results sorted by distance (lowest first = best match)
        mock_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc B (best)", "doc A (second)"]],
            "metadatas": [[
                {"file_path": "b.pdf", "source": "paperless", "created": "2024-01-01"},
                {"file_path": "a.pdf", "source": "paperless", "created": "2025-11-01"},
            ]],
            "distances": [[0.1, 0.2]],  # b.pdf has best score (lowest distance)
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        with patch("rag_api.search.embed_query", return_value=[0.1] * 768):
            results = searcher.semantic_search("test", top_k=5, sort_by_date=False, expand_links=False)

        # Default: ChromaDB order (by score) — b.pdf first (score 0.9)
        assert results[0]["file_path"] == "b.pdf"
        assert results[1]["file_path"] == "a.pdf"


# ---------------------------------------------------------------------------
# Hybrid search
# ---------------------------------------------------------------------------


class TestHybridSearch:
    def test_hybrid_forwards_sort_by_date_and_expand_links(self):
        from rag_api.search import Searcher

        searcher = Searcher.__new__(Searcher)

        with patch.object(searcher, "semantic_search", return_value=[]) as mock_semantic, \
             patch.object(searcher, "keyword_search", return_value=[]):
            searcher.hybrid_search(
                "test query",
                top_k=5,
                expand_links=False,
                sort_by_date=True,
            )

        mock_semantic.assert_called_once_with(
            "test query",
            top_k=50,
            expand_links=False,
            paperless_tags=None,
            paperless_correspondent=None,
            paperless_created_year=None,
            paperless_document_type=None,
            sort_by_date=True,
            min_score=0.0,
        )

    def test_hybrid_merges_semantic_and_keyword(self):
        from rag_api.search import Searcher

        searcher = Searcher.__new__(Searcher)

        sem_results = [
            {"file_path": "a.pdf", "section": "", "score": 0.85, "source": "paperless", "match_type": "semantic", "content": "test query content a"},
            {"file_path": "b.pdf", "section": "", "score": 0.75, "source": "paperless", "match_type": "semantic", "content": "test query content b"},
        ]
        kw_results = [
            {"file_path": "b.pdf", "section": "", "score": 0.90, "source": "paperless", "match_type": "content", "content": "test query content b"},
            {"file_path": "c.pdf", "section": "", "score": 0.80, "source": "paperless", "match_type": "content", "content": "test query content c"},
        ]

        with patch.object(searcher, "semantic_search", return_value=sem_results), \
             patch.object(searcher, "keyword_search", return_value=kw_results):
            results = searcher.hybrid_search("test query", top_k=5)

        # Should have 3 unique results: a.pdf, b.pdf (boosted), c.pdf
        fps = [r["file_path"] for r in results]
        assert len(results) == 3
        assert "a.pdf" in fps
        assert "b.pdf" in fps
        assert "c.pdf" in fps

        # b.pdf appeared in both → cross-method bonus + full keyword coverage
        b_result = next(r for r in results if r["file_path"] == "b.pdf")
        assert b_result["score"] > 0.90

    def test_hybrid_applies_min_score(self):
        from rag_api.search import Searcher

        searcher = Searcher.__new__(Searcher)

        sem_results = [
            {"file_path": "a.pdf", "section": "", "score": 0.95, "source": "paperless", "match_type": "semantic", "content": "test content a"},
            {"file_path": "b.pdf", "section": "", "score": 0.65, "source": "paperless", "match_type": "semantic", "content": "test content b"},
        ]
        kw_results = []

        with patch.object(searcher, "semantic_search", return_value=sem_results), \
             patch.object(searcher, "keyword_search", return_value=kw_results):
            # Coverage for "test": both docs contain "test" → full coverage → ×1.0
            results = searcher.hybrid_search("test", top_k=5, min_score=0.70)

        assert len(results) == 1
        assert results[0]["file_path"] == "a.pdf"

    def test_hybrid_respects_sort_by_date(self):
        from rag_api.search import Searcher

        searcher = Searcher.__new__(Searcher)

        sem_results = [
            {"file_path": "old.pdf", "section": "", "score": 0.90, "source": "paperless",
             "match_type": "semantic", "created": "2024-01-01", "content": "recent doc"},
            {"file_path": "new.pdf", "section": "", "score": 0.80, "source": "paperless",
             "match_type": "semantic", "created": "2025-11-01", "content": "recent doc"},
        ]
        kw_results = []

        with patch.object(searcher, "semantic_search", return_value=sem_results), \
             patch.object(searcher, "keyword_search", return_value=kw_results):
            results = searcher.hybrid_search("test", top_k=5, sort_by_date=True)

        assert results[0]["file_path"] == "new.pdf"
        assert results[1]["file_path"] == "old.pdf"

    def test_hybrid_sort_by_date_uses_created_from_keyword_hits(self):
        from rag_api.search import Searcher

        searcher = Searcher.__new__(Searcher)

        sem_results = []
        kw_results = [
            {"file_path": "old.pdf", "section": "", "score": 0.95, "source": "paperless",
             "match_type": "content", "created": "2024-01-01", "content": "invoice"},
            {"file_path": "new.pdf", "section": "", "score": 0.80, "source": "paperless",
             "match_type": "content", "created": "2025-11-01", "content": "invoice"},
        ]

        with patch.object(searcher, "semantic_search", return_value=sem_results), \
             patch.object(searcher, "keyword_search", return_value=kw_results):
            results = searcher.hybrid_search("invoice", top_k=5, sort_by_date=True)

        assert results[0]["file_path"] == "new.pdf"
        assert results[1]["file_path"] == "old.pdf"

    def test_keyword_search_includes_created_metadata(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer._file_sources = {}
        mock_indexer._file_path_from_key = lambda k: k.split("::", 1)[1]

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["invoice content"],
            "metadatas": [{
                "file_path": "invoice.pdf",
                "section": "",
                "source": "paperless",
                "created": "2025-11-01",
            }],
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        results = searcher.keyword_search("invoice", top_k=5)

        assert results[0]["created"] == "2025-11-01"

    def test_filename_match_gets_created_from_content_metadata(self):
        """Filename matches should backfill `created` from content metadata."""
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer._file_sources = {"paperless::invoice.pdf": "paperless"}
        mock_indexer._file_path_from_key = lambda k: k.split("::", 1)[1]

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["invoice total 500 EUR"],
            "metadatas": [{
                "file_path": "invoice.pdf",
                "section": "",
                "source": "paperless",
                "created": "2025-06-15",
            }],
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        results = searcher.keyword_search("invoice", top_k=5)

        # Filename match should have created backfilled
        filename_results = [r for r in results if r["match_type"] == "filename"]
        assert len(filename_results) == 1
        assert filename_results[0].get("created") == "2025-06-15"


class TestMultiWordDocumentScope:
    """Multi-word AND should match across chunks of the same document."""

    def _make_searcher(self, docs, metadatas):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer._file_sources = {}
        mock_indexer._file_path_from_key = lambda k: k.split("::", 1)[1]

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": docs,
            "metadatas": metadatas,
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection
        return searcher

    def test_terms_split_across_chunks_still_match(self):
        """If term A is in chunk 1 and term B is in chunk 2 of the same doc, it should match."""
        docs = [
            "Der Kaufvertrag wurde am 01.01.2020 geschlossen",
            "Das Grundstück befindet sich in Montabaur",
        ]
        metas = [
            {"file_path": "vertrag.pdf", "section": "1", "source": "paperless"},
            {"file_path": "vertrag.pdf", "section": "2", "source": "paperless"},
        ]
        searcher = self._make_searcher(docs, metas)
        results = searcher.keyword_search("kaufvertrag grundstück", top_k=5)

        # Should find vertrag.pdf even though terms are in different chunks
        fps = [r["file_path"] for r in results]
        assert "vertrag.pdf" in fps

    def test_unrelated_doc_not_matched(self):
        """A document that only has one of two terms across all chunks should not match."""
        docs = [
            "Kaufvertrag Audi e-tron",
            "Wartung und Inspektion",
        ]
        metas = [
            {"file_path": "auto.pdf", "section": "1", "source": "paperless"},
            {"file_path": "auto.pdf", "section": "2", "source": "paperless"},
        ]
        searcher = self._make_searcher(docs, metas)
        results = searcher.keyword_search("kaufvertrag grundstück", top_k=5)

        assert len(results) == 0


class TestMinScoreDateSort:
    """min_score should be applied before truncating date-sorted semantic results."""

    def test_min_score_filters_before_top_k_truncation(self):
        from rag_api.search import Searcher

        mock_indexer = MagicMock()
        mock_indexer.link_graph = None

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5

        # 5 results: 2 high-score, 3 low-score but newer
        mock_collection.query.return_value = {
            "ids": [["id1", "id2", "id3", "id4", "id5"]],
            "documents": [["old good", "old good 2", "new bad", "new bad 2", "new bad 3"]],
            "metadatas": [[
                {"file_path": "a.pdf", "section": "1", "source": "paperless", "created": "2024-01-01"},
                {"file_path": "b.pdf", "section": "1", "source": "paperless", "created": "2024-02-01"},
                {"file_path": "c.pdf", "section": "1", "source": "paperless", "created": "2025-11-01"},
                {"file_path": "d.pdf", "section": "1", "source": "paperless", "created": "2025-12-01"},
                {"file_path": "e.pdf", "section": "1", "source": "paperless", "created": "2025-12-15"},
            ]],
            "distances": [[0.1, 0.15, 0.7, 0.75, 0.8]],  # c,d,e have low scores (0.3, 0.25, 0.2)
        }

        searcher = Searcher.__new__(Searcher)
        searcher.indexer = mock_indexer
        searcher.collection = mock_collection

        with patch("rag_api.search.embed_query", return_value=[0.1] * 768):
            results = searcher.semantic_search(
                "test", top_k=3, sort_by_date=True,
                min_score=0.5, expand_links=False,
            )

        # Only a.pdf (0.9) and b.pdf (0.85) pass min_score; c/d/e are below 0.5
        assert len(results) == 2
        fps = [r["file_path"] for r in results]
        assert "a.pdf" in fps
        assert "b.pdf" in fps


class TestPaperlessLookupFallback:
    """When Paperless API is unreachable, filters should fall back to metadata."""

    def test_incomplete_tag_cache_returns_none(self):
        """If tag lookup didn't complete (partial fetch), return None for fallback."""
        from rag_api.search import (
            _query_paperless_api, _TAG_NAME_TO_ID, _DOCTYPE_NAME_TO_ID,
            _CORR_NAME_TO_ID, _LOOKUP_COMPLETE,
        )

        saved = (dict(_TAG_NAME_TO_ID), dict(_DOCTYPE_NAME_TO_ID), dict(_CORR_NAME_TO_ID))
        saved_complete = dict(_LOOKUP_COMPLETE)
        try:
            # Simulate partial cache: some tags loaded but lookup incomplete
            _TAG_NAME_TO_ID.clear()
            _TAG_NAME_TO_ID["page1tag"] = 1
            _DOCTYPE_NAME_TO_ID.clear()
            _CORR_NAME_TO_ID.clear()
            _LOOKUP_COMPLETE["tags"] = False
            _LOOKUP_COMPLETE["doctypes"] = False
            _LOOKUP_COMPLETE["corrs"] = False

            with patch("rag_api.search._ensure_paperless_lookups"):
                result = _query_paperless_api(tags=["page2tag"])

            # Incomplete cache → should return None (fallback), not [] (no match)
            assert result is None
        finally:
            _TAG_NAME_TO_ID.clear()
            _TAG_NAME_TO_ID.update(saved[0])
            _DOCTYPE_NAME_TO_ID.clear()
            _DOCTYPE_NAME_TO_ID.update(saved[1])
            _CORR_NAME_TO_ID.clear()
            _CORR_NAME_TO_ID.update(saved[2])
            _LOOKUP_COMPLETE.update(saved_complete)

    def test_complete_cache_unknown_tag_returns_empty(self):
        """If cache is fully populated but tag doesn't exist, return [] (genuine no match)."""
        from rag_api.search import (
            _query_paperless_api, _TAG_NAME_TO_ID, _DOCTYPE_NAME_TO_ID,
            _CORR_NAME_TO_ID, _LOOKUP_COMPLETE,
        )

        saved = (dict(_TAG_NAME_TO_ID), dict(_DOCTYPE_NAME_TO_ID), dict(_CORR_NAME_TO_ID))
        saved_complete = dict(_LOOKUP_COMPLETE)
        try:
            _TAG_NAME_TO_ID.clear()
            _TAG_NAME_TO_ID["vorhanden"] = 42
            _DOCTYPE_NAME_TO_ID.clear()
            _CORR_NAME_TO_ID.clear()
            _LOOKUP_COMPLETE["tags"] = True
            _LOOKUP_COMPLETE["doctypes"] = True
            _LOOKUP_COMPLETE["corrs"] = True

            with patch("rag_api.search._ensure_paperless_lookups"):
                result = _query_paperless_api(tags=["Unbekannt"])

            assert result == []
        finally:
            _TAG_NAME_TO_ID.clear()
            _TAG_NAME_TO_ID.update(saved[0])
            _DOCTYPE_NAME_TO_ID.clear()
            _DOCTYPE_NAME_TO_ID.update(saved[1])
            _CORR_NAME_TO_ID.clear()
            _CORR_NAME_TO_ID.update(saved[2])
            _LOOKUP_COMPLETE.update(saved_complete)

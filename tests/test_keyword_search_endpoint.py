"""Tests for POST /keyword-search and /documents request validation."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from rag_api.api import DocumentsRequest, SearchRequest, app


@pytest.fixture(autouse=True)
def _patch_searcher(monkeypatch):
    """Provide a fake searcher so keyword endpoint behavior is easy to assert."""
    fake_searcher = MagicMock()
    fake_searcher.keyword_search.return_value = [
        {
            "file_path": "paperless/42.pdf",
            "section": "",
            "content": "",
            "score": 1.0,
            "match_type": "filename",
            "source": "paperless",
        }
    ]
    monkeypatch.setattr("rag_api.api.searcher", fake_searcher)
    return fake_searcher


@pytest.fixture()
def client():
    return TestClient(app)


class TestKeywordSearchEndpoint:
    def test_query_still_works(self, client, _patch_searcher):
        resp = client.post("/keyword-search", json={"query": "NVR"})

        assert resp.status_code == 200
        _patch_searcher.keyword_search.assert_called_once_with(
            "NVR",
            5,
            paperless_tags=None,
            paperless_correspondent=None,
            paperless_created_year=None,
            paperless_document_type=None,
        )

    def test_filter_only_request_returns_422(self, client, _patch_searcher):
        resp = client.post(
            "/keyword-search",
            json={
                "paperless_correspondent": "Kreisverwaltung Westerwaldkreis",
                "paperless_tags": ["nick"],
            },
        )

        assert resp.status_code == 422
        _patch_searcher.keyword_search.assert_not_called()

    def test_empty_request_still_returns_422(self, client, _patch_searcher):
        resp = client.post("/keyword-search", json={})

        assert resp.status_code == 422
        assert "query" in str(resp.json()["detail"]).lower()
        _patch_searcher.keyword_search.assert_not_called()

    def test_blank_query_returns_422(self, client, _patch_searcher):
        resp = client.post("/keyword-search", json={"query": "   "})

        assert resp.status_code == 422
        assert "query must not be empty" in resp.json()["detail"]
        _patch_searcher.keyword_search.assert_not_called()


class TestDocumentsEndpoint:
    def test_filter_only_documents_request_is_allowed(self, client, _patch_searcher):
        _patch_searcher.list_documents.return_value = [
            {
                "file_path": "paperless/42.pdf",
                "section": "",
                "content": "",
                "score": 1.0,
                "match_type": "content",
                "source": "paperless",
                "created": "2026-04-10",
            }
        ]

        resp = client.post(
            "/documents",
            json={
                "paperless_correspondent": "Kreisverwaltung Westerwaldkreis",
                "paperless_tags": ["nick"],
            },
        )

        assert resp.status_code == 200
        _patch_searcher.list_documents.assert_called_once_with(
            10,
            paperless_tags=["nick"],
            paperless_correspondent="Kreisverwaltung Westerwaldkreis",
            paperless_created_year=None,
            paperless_document_type=None,
            sort_by_date=True,
        )

    def test_documents_requires_filter(self, client, _patch_searcher):
        resp = client.post("/documents", json={})

        assert resp.status_code == 422
        assert "At least one paperless_* filter is required for /documents" in resp.json()["detail"]
        _patch_searcher.list_documents.assert_not_called()

    def test_documents_rejects_blank_filter_values(self, client, _patch_searcher):
        resp = client.post(
            "/documents",
            json={
                "paperless_correspondent": "   ",
                "paperless_tags": [""],
                "paperless_created_year": 0,
            },
        )

        assert resp.status_code == 422
        assert "At least one paperless_* filter is required for /documents" in resp.json()["detail"]
        _patch_searcher.list_documents.assert_not_called()

    def test_documents_sanitizes_mixed_filter_values(self, client, _patch_searcher):
        _patch_searcher.list_documents.return_value = []

        resp = client.post(
            "/documents",
            json={
                "paperless_correspondent": "   ",
                "paperless_tags": ["nick", ""],
                "paperless_created_year": 0,
                "paperless_document_type": " Bescheid ",
            },
        )

        assert resp.status_code == 200
        _patch_searcher.list_documents.assert_called_once_with(
            10,
            paperless_tags=["nick"],
            paperless_correspondent=None,
            paperless_created_year=None,
            paperless_document_type="Bescheid",
            sort_by_date=True,
        )

    def test_documents_rejects_non_positive_top_k(self, client, _patch_searcher):
        resp = client.post(
            "/documents",
            json={
                "top_k": 0,
                "paperless_tags": ["nick"],
            },
        )

        assert resp.status_code == 422
        assert "greater than or equal to 1" in str(resp.json()["detail"]).lower()
        _patch_searcher.list_documents.assert_not_called()


class TestRequestModels:
    def test_search_request_requires_query(self):
        req = SearchRequest(query="NVR")

        assert req.query == "NVR"

    def test_documents_request_parses_filters(self):
        req = DocumentsRequest(paperless_tags=["nick"])

        assert req.paperless_tags == ["nick"]
        assert req.sort_by_date is True

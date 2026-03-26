"""Tests for the POST /note endpoint resilience (empty body, query-param fallback)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from rag_api.api import app, NoteRequest


@pytest.fixture(autouse=True)
def _patch_searcher(monkeypatch):
    """Provide a fake searcher so the endpoint can resolve notes."""
    fake_searcher = MagicMock()
    fake_searcher.get_note.side_effect = lambda p: (
        {"file_path": p, "content": "# Hello"} if p == "notes/Test.md" else None
    )
    monkeypatch.setattr("rag_api.api.searcher", fake_searcher)


@pytest.fixture()
def client():
    return TestClient(app)


class TestPostNoteEmptyBody:
    """Regression: n8n sometimes sends POST /note with an empty JSON body."""

    def test_empty_body_returns_422_with_helpful_message(self, client):
        resp = client.post("/note", json={})
        assert resp.status_code == 422
        assert "path is required" in resp.json()["detail"]

    def test_empty_body_with_query_param_fallback(self, client):
        resp = client.post("/note?path=notes/Test.md", json={})
        assert resp.status_code == 200
        assert resp.json()["file_path"] == "notes/Test.md"

    def test_body_path_takes_precedence_over_query_param(self, client):
        resp = client.post("/note?path=ignored.md", json={"path": "notes/Test.md"})
        assert resp.status_code == 200
        assert resp.json()["file_path"] == "notes/Test.md"

    def test_normal_body_still_works(self, client):
        resp = client.post("/note", json={"path": "notes/Test.md"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "# Hello"

    def test_not_found_returns_404(self, client):
        resp = client.post("/note", json={"path": "nonexistent.md"})
        assert resp.status_code == 404


class TestNoteRequestModel:
    """NoteRequest.path is now Optional to tolerate empty bodies."""

    def test_empty_dict_parses(self):
        req = NoteRequest()
        assert req.path is None

    def test_path_parses(self):
        req = NoteRequest(path="notes/Test.md")
        assert req.path == "notes/Test.md"


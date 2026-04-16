"""Tests for persistent per-message agent call budgets."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from rag_api.agent_budget import AgentCallBudgetStore
from rag_api.api import app


@pytest.fixture(autouse=True)
def _patch_searcher(monkeypatch):
    """Provide a fake searcher so search endpoints can run in isolation."""
    fake_searcher = MagicMock()
    fake_searcher.keyword_search.return_value = [
        {
            "file_path": "notes/Test.md",
            "content": "match",
            "score": 1.0,
            "source": "obsidian",
        }
    ]
    monkeypatch.setattr("rag_api.api.searcher", fake_searcher)


@pytest.fixture()
def budget_db_path(tmp_path: Path) -> Path:
    return tmp_path / "agent-budget.sqlite3"


@pytest.fixture()
def client(monkeypatch, budget_db_path: Path):
    monkeypatch.setattr(
        "rag_api.api.agent_call_budget",
        AgentCallBudgetStore(str(budget_db_path), 2),
    )
    return TestClient(app)


def test_requests_without_headers_are_not_limited(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_missing_headers_return_400_when_budget_is_enabled(client):
    resp = client.post("/keyword-search", json={"query": "NVR"})
    assert resp.status_code == 400
    assert "x-rag-conversation-id" in resp.json()["detail"]
    assert "x-rag-message-id" in resp.json()["detail"]


def test_third_call_returns_429(client):
    headers = {
        "x-rag-conversation-id": "conv-1",
        "x-rag-message-id": "msg-1",
    }

    first = client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert first.status_code == 200
    assert first.headers["X-RAG-Call-Count"] == "1"
    assert first.headers["X-RAG-Remaining-Calls"] == "1"

    second = client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert second.status_code == 200
    assert second.headers["X-RAG-Call-Count"] == "2"
    assert second.headers["X-RAG-Remaining-Calls"] == "0"

    third = client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert third.status_code == 429
    assert third.json()["call_count"] == 3
    assert third.json()["max_calls"] == 2


def test_counter_is_persistent_across_store_instances(client, monkeypatch, budget_db_path: Path):
    headers = {
        "x-rag-conversation-id": "conv-2",
        "x-rag-message-id": "msg-2",
    }

    first = client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert first.status_code == 200

    monkeypatch.setattr(
        "rag_api.api.agent_call_budget",
        AgentCallBudgetStore(str(budget_db_path), 2),
    )
    restarted_client = TestClient(app)

    second = restarted_client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert second.status_code == 200
    assert second.headers["X-RAG-Call-Count"] == "2"

    third = restarted_client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert third.status_code == 429


def test_budget_state_and_reset_endpoints(client):
    headers = {
        "x-rag-conversation-id": "conv-3",
        "x-rag-message-id": "msg-3",
    }
    client.post("/keyword-search", json={"query": "NVR"}, headers=headers)

    state = client.get("/agent-call-budget?conversation_id=conv-3&message_id=msg-3")
    assert state.status_code == 200
    assert state.json()["call_count"] == 1
    assert state.json()["remaining_calls"] == 1

    reset = client.post(
        "/agent-call-budget/reset",
        json={"conversation_id": "conv-3", "message_id": "msg-3"},
    )
    assert reset.status_code == 200
    assert reset.json()["deleted_counters"] == 1

    state_after_reset = client.get(
        "/agent-call-budget?conversation_id=conv-3&message_id=msg-3"
    )
    assert state_after_reset.status_code == 200
    assert state_after_reset.json()["call_count"] == 0


def test_failed_requests_do_not_consume_budget(client):
    headers = {
        "x-rag-conversation-id": "conv-4",
        "x-rag-message-id": "msg-4",
    }

    invalid = client.post("/note", json={}, headers=headers)
    assert invalid.status_code == 422
    assert invalid.headers["X-RAG-Call-Count"] == "0"
    assert invalid.headers["X-RAG-Remaining-Calls"] == "2"

    valid = client.post("/keyword-search", json={"query": "NVR"}, headers=headers)
    assert valid.status_code == 200
    assert valid.headers["X-RAG-Call-Count"] == "1"

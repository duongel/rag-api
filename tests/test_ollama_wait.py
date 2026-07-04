"""Tests for Ollama readiness + automatic embedding-model pull."""

import json

import pytest

from rag_api import main


class _FakeTagsResponse:
    def __init__(self, models):
        self.ok = True
        self._models = models

    def json(self):
        return {"models": [{"name": m} for m in self._models]}


class _FakePullResponse:
    def __init__(self, lines, ok=True, status_code=200, text=""):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._lines = lines

    def iter_lines(self):
        for line in self._lines:
            yield line


def test_returns_when_model_present(monkeypatch):
    calls = {"get": 0, "post": 0}

    def fake_get(url, timeout=None):
        calls["get"] += 1
        return _FakeTagsResponse([main.EMBED_MODEL])

    def fake_post(*args, **kwargs):
        calls["post"] += 1
        raise AssertionError("should not pull when model is present")

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.requests, "post", fake_post)

    main._wait_for_ollama()

    assert calls["get"] == 1
    assert calls["post"] == 0


def test_auto_pull_when_model_missing(monkeypatch):
    state = {"pulled": False, "post_calls": 0}

    def fake_get(url, timeout=None):
        models = [main.EMBED_MODEL] if state["pulled"] else ["some-other-model"]
        return _FakeTagsResponse(models)

    def fake_post(url, json=None, stream=None, timeout=None):
        state["post_calls"] += 1
        assert url.endswith("/api/pull")
        assert json["model"] == main.EMBED_MODEL
        state["pulled"] = True
        return _FakePullResponse(
            [b'{"status": "pulling manifest"}', b'{"status": "success"}']
        )

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "EMBED_MODEL_AUTO_PULL", True)

    main._wait_for_ollama()

    assert state["post_calls"] == 1


def test_no_pull_when_disabled_times_out(monkeypatch):
    def fake_get(url, timeout=None):
        return _FakeTagsResponse(["some-other-model"])

    def fake_post(*args, **kwargs):
        raise AssertionError("should not pull when auto-pull is disabled")

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "EMBED_MODEL_AUTO_PULL", False)
    monkeypatch.setattr(main, "OLLAMA_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="did not become ready"):
        main._wait_for_ollama()


def test_pull_failure_falls_back_to_timeout(monkeypatch):
    def fake_get(url, timeout=None):
        return _FakeTagsResponse(["some-other-model"])

    def fake_post(url, json=None, stream=None, timeout=None):
        return _FakePullResponse(
            [b'{"error": "pull failed"}'], ok=True
        )

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "EMBED_MODEL_AUTO_PULL", True)
    monkeypatch.setattr(main, "OLLAMA_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="did not become ready"):
        main._wait_for_ollama()

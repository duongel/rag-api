from rag_api.api import _enrich_source_url


def test_paperless_source_url_points_to_document_view(monkeypatch):
    monkeypatch.setattr("rag_api.api.PAPERLESS_PUBLIC_URL", "https://paperless.example.com")

    result = _enrich_source_url(
        {
            "source": "paperless",
            "file_path": "docs/invoice.pdf",
            "paperless_doc_id": "42",
        }
    )

    assert result["source_url"] == "https://paperless.example.com/api/documents/42/preview/"


def test_paperless_source_url_uses_numeric_stem_fallback(monkeypatch):
    monkeypatch.setattr("rag_api.api.PAPERLESS_PUBLIC_URL", "https://paperless.example.com/")

    result = _enrich_source_url(
        {
            "source": "paperless",
            "file_path": "paperless/77.pdf",
        }
    )

    assert result["source_url"] == "https://paperless.example.com/api/documents/77/preview/"


def test_truncate_content_shortens_when_over_limit():
    from rag_api.api import _truncate_content

    result = _truncate_content({"content": "x" * 1000}, 300)
    assert len(result["content"]) == 300


def test_truncate_content_noop_when_none():
    from rag_api.api import _truncate_content

    result = _truncate_content({"content": "x" * 1000}, None)
    assert len(result["content"]) == 1000


def test_truncate_content_noop_when_under_limit():
    from rag_api.api import _truncate_content

    result = _truncate_content({"content": "short"}, 300)
    assert result["content"] == "short"


def test_search_request_accepts_max_content_chars():
    from rag_api.api import SearchRequest

    req = SearchRequest(query="x", max_content_chars=200)
    assert req.max_content_chars == 200
    assert SearchRequest(query="x").max_content_chars is None

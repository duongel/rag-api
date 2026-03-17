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

    assert result["source_url"] == "https://paperless.example.com/documents/42/document"


def test_paperless_source_url_uses_numeric_stem_fallback(monkeypatch):
    monkeypatch.setattr("rag_api.api.PAPERLESS_PUBLIC_URL", "https://paperless.example.com/")

    result = _enrich_source_url(
        {
            "source": "paperless",
            "file_path": "paperless/77.pdf",
        }
    )

    assert result["source_url"] == "https://paperless.example.com/documents/77/document"

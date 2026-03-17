"""Tests for Paperless indexing and webhook flows.

Uses an in-memory ChromaDB and mocks embed_documents to avoid
needing a running Ollama instance.
"""

from unittest.mock import MagicMock, patch
import os

import pytest

# Ensure config defaults are safe for testing (no external services)
os.environ.setdefault("CHROMA_PATH", "/tmp/test_chroma")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("PAPERLESS_URL", "http://paperless:8000")
os.environ.setdefault("PAPERLESS_TOKEN", "test-token")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBED_DIM = 8


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Return deterministic fake embeddings."""
    return [[float(i)] * EMBED_DIM for i in range(len(texts))]


def _make_doc(doc_id: int, content: str = "some content", archive_filename: str | None = None, **extra):
    doc = {"id": doc_id, "content": content, **extra}
    if archive_filename is not None:
        doc["archive_filename"] = archive_filename
    return doc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def indexer():
    """Create an Indexer backed by an ephemeral in-memory ChromaDB."""
    import chromadb

    ephemeral = chromadb.EphemeralClient()

    with (
        patch("rag_api.indexer.embed_documents", side_effect=_fake_embed),
        patch("rag_api.indexer.chromadb.PersistentClient", return_value=ephemeral),
    ):
        from rag_api.indexer import Indexer
        idx = Indexer()
        yield idx


# ===========================================================================
# index_paperless_doc
# ===========================================================================

class TestIndexPaperlessDoc:
    def test_index_new_doc(self, indexer):
        doc = _make_doc(1, content="Hello world from Paperless")
        assert indexer.index_paperless_doc(doc) is True
        # Verify chunks are in Chroma
        results = indexer.collection.get(where={"paperless_doc_id": "1"})
        assert len(results["ids"]) > 0

    def test_unchanged_doc_returns_false(self, indexer):
        doc = _make_doc(2, content="Static content")
        assert indexer.index_paperless_doc(doc) is True
        assert indexer.index_paperless_doc(doc) is False

    def test_updated_content_reindexes(self, indexer):
        doc = _make_doc(3, content="Version 1")
        assert indexer.index_paperless_doc(doc) is True

        doc["content"] = "Version 2 with different text"
        assert indexer.index_paperless_doc(doc) is True

    def test_metadata_only_change_reindexes(self, indexer):
        doc = _make_doc(13, content="Stable OCR", title="Invoice", tags=[1])
        assert indexer.index_paperless_doc(doc) is True

        # OCR text unchanged, only metadata changed
        doc["tags"] = [1, 2]
        assert indexer.index_paperless_doc(doc) is True

        results = indexer.collection.get(where={"paperless_doc_id": "13"}, include=["documents", "metadatas"])
        assert results["documents"]
        assert "Tags: 1,2" in results["documents"][0]
        assert results["metadatas"][0]["tags"] == "1,2"

    def test_no_id_returns_false(self, indexer):
        assert indexer.index_paperless_doc({}) is False

    def test_empty_content_with_key_removes_doc(self, indexer):
        doc = _make_doc(4, content="Has content initially")
        indexer.index_paperless_doc(doc)

        empty_doc = _make_doc(4, content="")
        assert indexer.index_paperless_doc(empty_doc) is False
        # Chunks should be removed
        results = indexer.collection.get(where={"paperless_doc_id": "4"})
        assert len(results["ids"]) == 0

    def test_missing_content_key_does_not_remove(self, indexer):
        doc = _make_doc(5, content="Existing content")
        indexer.index_paperless_doc(doc)

        # Payload without content key (e.g. summary-only list response)
        no_content_doc = {"id": 5}
        indexer.index_paperless_doc(no_content_doc)

        # Chunks should still exist
        results = indexer.collection.get(where={"paperless_doc_id": "5"})
        assert len(results["ids"]) > 0

    def test_archive_filename_used_as_path(self, indexer):
        doc = _make_doc(6, content="Content", archive_filename="docs/invoice.pdf")
        indexer.index_paperless_doc(doc)

        results = indexer.collection.get(where={"paperless_doc_id": "6"}, include=["metadatas"])
        assert all(m["file_path"] == "docs/invoice.pdf" for m in results["metadatas"])

    def test_synthetic_path_when_no_archive_filename(self, indexer):
        doc = _make_doc(7, content="Content")
        indexer.index_paperless_doc(doc)

        results = indexer.collection.get(where={"paperless_doc_id": "7"}, include=["metadatas"])
        assert all(m["file_path"] == "paperless/7.pdf" for m in results["metadatas"])

    def test_rename_cleans_old_path(self, indexer):
        """When archive_filename changes, old path chunks are removed."""
        doc = _make_doc(8, content="Content for rename test", archive_filename="old_name.pdf")
        indexer.index_paperless_doc(doc)

        # Rename: same content, different path
        doc["archive_filename"] = "new_name.pdf"
        assert indexer.index_paperless_doc(doc) is True

        # Old path should be gone
        old_results = indexer.collection.get(
            where={"$and": [{"file_path": "old_name.pdf"}, {"source": "paperless"}]}
        )
        assert len(old_results["ids"]) == 0

        # New path should exist
        new_results = indexer.collection.get(
            where={"$and": [{"file_path": "new_name.pdf"}, {"source": "paperless"}]}
        )
        assert len(new_results["ids"]) > 0

    def test_metadata_stored(self, indexer):
        doc = _make_doc(
            9,
            content="Doc with metadata",
            title="Invoice 2024",
            correspondent=42,
            tags=[1, 2, 3],
            created="2024-01-15",
        )
        indexer.index_paperless_doc(doc)

        results = indexer.collection.get(where={"paperless_doc_id": "9"}, include=["metadatas"])
        meta = results["metadatas"][0]
        assert meta["title"] == "Invoice 2024"
        assert meta["correspondent"] == "42"
        assert meta["tags"] == "1,2,3"
        assert meta["created"] == "2024-01-15"

    def test_metadata_is_embedded_into_indexed_chunk_text(self, indexer):
        doc = _make_doc(
            12,
            content="OCR body text",
            title="Gas Invoice",
            correspondent=7,
            tags=[10, 11],
        )

        assert indexer.index_paperless_doc(doc) is True

        results = indexer.collection.get(
            where={"paperless_doc_id": "12"}, include=["documents", "metadatas"]
        )
        assert results["documents"]
        chunk_text = results["documents"][0]
        assert "Paperless Metadata" in chunk_text
        assert "Title: Gas Invoice" in chunk_text
        assert "Correspondent: 7" in chunk_text
        assert "Tags: 10,11" in chunk_text
        assert chunk_text.endswith("OCR body text")


# ===========================================================================
# remove_paperless_doc
# ===========================================================================

class TestRemovePaperlessDoc:
    def test_remove_by_synthetic_path(self, indexer):
        doc = _make_doc(10, content="To be removed")
        indexer.index_paperless_doc(doc)
        assert len(indexer.collection.get(where={"paperless_doc_id": "10"})["ids"]) > 0

        indexer.remove_paperless_doc(10)
        assert len(indexer.collection.get(where={"paperless_doc_id": "10"})["ids"]) == 0

    def test_remove_by_archive_filename(self, indexer):
        doc = _make_doc(11, content="Named doc", archive_filename="named.pdf")
        indexer.index_paperless_doc(doc)

        indexer.remove_paperless_doc(11)
        results = indexer.collection.get(where={"paperless_doc_id": "11"})
        assert len(results["ids"]) == 0

    def test_remove_nonexistent_is_noop(self, indexer):
        # Should not raise
        indexer.remove_paperless_doc(99999)


# ===========================================================================
# Webhook endpoint
# ===========================================================================

class TestPaperlessWebhook:
    @pytest.fixture(autouse=True)
    def _setup_app(self, indexer):
        """Inject the test indexer into the API module."""
        from rag_api import api
        from fastapi.testclient import TestClient

        api.indexer = indexer
        self.indexer = indexer
        self.client = TestClient(api.app)

    def test_webhook_updated_indexes_doc(self):
        # Mock reindex_paperless_doc to return True (indexed)
        self.indexer.reindex_paperless_doc = MagicMock(return_value=True)
        resp = self.client.post(
            "/webhook/paperless",
            json={"document_id": 100, "action": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "indexed"
        self.indexer.reindex_paperless_doc.assert_called_once_with(100)

    def test_webhook_deleted_removes_doc(self):
        self.indexer.remove_paperless_doc = MagicMock()
        resp = self.client.post(
            "/webhook/paperless",
            json={"document_id": 101, "action": "deleted"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"
        self.indexer.remove_paperless_doc.assert_called_once_with(101)

    def test_webhook_failure_returns_502(self):
        self.indexer.reindex_paperless_doc = MagicMock(
            side_effect=RuntimeError("API unreachable")
        )
        resp = self.client.post(
            "/webhook/paperless",
            json={"document_id": 102, "action": "added"},
        )
        assert resp.status_code == 502
        assert resp.json()["status"] == "error"

    def test_webhook_unchanged_doc(self):
        self.indexer.reindex_paperless_doc = MagicMock(return_value=False)
        resp = self.client.post(
            "/webhook/paperless",
            json={"document_id": 103, "action": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "unchanged"


# ===========================================================================
# get_note for Paperless documents (retrieved from ChromaDB)
# ===========================================================================

class TestGetNotePaperless:
    @pytest.fixture(autouse=True)
    def _setup(self, indexer):
        with patch("rag_api.search.embed_query", side_effect=lambda q: [0.0] * EMBED_DIM):
            from rag_api.search import Searcher
            self.indexer = indexer
            self.searcher = Searcher(indexer)

    def test_paperless_doc_found_by_archive_filename(self):
        doc = _make_doc(50, content="Hello from Paperless", archive_filename="vertrag/test.pdf")
        self.indexer.index_paperless_doc(doc)
        result = self.searcher.get_note("vertrag/test.pdf")
        assert result is not None
        assert result["file_path"] == "vertrag/test.pdf"
        assert "Hello from Paperless" in result["content"]
        assert result["source"] == "paperless"

    def test_paperless_doc_found_by_synthetic_path(self):
        doc = _make_doc(77, content="Synthetic path doc")
        self.indexer.index_paperless_doc(doc)
        result = self.searcher.get_note("paperless/77.pdf")
        assert result is not None
        assert "Synthetic path doc" in result["content"]

    def test_paperless_doc_not_found(self):
        result = self.searcher.get_note("nonexistent/path.pdf")
        assert result is None

    def test_paperless_doc_includes_doc_id(self):
        doc = _make_doc(99, content="Doc with ID", archive_filename="invoices/inv.pdf")
        self.indexer.index_paperless_doc(doc)
        result = self.searcher.get_note("invoices/inv.pdf")
        assert result is not None
        assert result["paperless_doc_id"] == "99"

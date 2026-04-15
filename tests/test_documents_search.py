"""Tests for metadata-only Paperless document listing."""

from unittest.mock import MagicMock

from rag_api.search import Searcher


class TestListDocuments:
    def test_deduplicates_to_best_chunk_per_document_and_sorts_by_date(self):
        indexer = MagicMock()
        indexer.collection.get.return_value = {
            "documents": [
                "later chunk doc 1",
                "first chunk doc 1",
                "only chunk doc 2",
            ],
            "metadatas": [
                {
                    "source": "paperless",
                    "file_path": "paperless/1.pdf",
                    "chunk_index": 3,
                    "paperless_doc_id": "1",
                    "created": "2026-04-01",
                },
                {
                    "source": "paperless",
                    "file_path": "paperless/1.pdf",
                    "chunk_index": 0,
                    "paperless_doc_id": "1",
                    "created": "2026-04-01",
                },
                {
                    "source": "paperless",
                    "file_path": "paperless/2.pdf",
                    "chunk_index": 0,
                    "paperless_doc_id": "2",
                    "created": "2026-04-10",
                },
            ],
        }

        searcher = Searcher(indexer)

        results = searcher.list_documents(paperless_tags=["nick"])

        assert [result["file_path"] for result in results] == [
            "paperless/2.pdf",
            "paperless/1.pdf",
        ]
        assert results[1]["content"] == "first chunk doc 1"

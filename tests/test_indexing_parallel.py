"""Tests for parallel full reindexing and LinkGraph thread-safety.

Uses an in-memory ChromaDB and mocks embed_documents so no running Ollama
instance is required.
"""

import threading
from unittest.mock import patch

import pytest

EMBED_DIM = 8


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Return deterministic fake embeddings."""
    return [[float(i + 1)] * EMBED_DIM for i in range(len(texts))]


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

        yield Indexer()


def _write_vault(root, n: int) -> None:
    """Create *n* markdown files; the last one links to the first."""
    for i in range(n):
        body = f"# Note {i}\n\nContent for note number {i}.\n"
        if i == n - 1:
            body += "\nSee also [[note_0]].\n"
        (root / f"note_{i}.md").write_text(body, encoding="utf-8")


class TestParallelFullReindex:
    def test_indexes_all_files(self, indexer, tmp_path):
        _write_vault(tmp_path, 12)

        count = indexer.full_reindex(base_path=str(tmp_path), source="obsidian")

        assert count == 12
        # Every file contributed at least one chunk to the collection.
        indexed_paths = {
            m["file_path"] for m in indexer.collection.get(include=["metadatas"])["metadatas"]
        }
        assert indexed_paths == {f"note_{i}.md" for i in range(12)}

    def test_progress_reports_reach_total(self, indexer, tmp_path):
        _write_vault(tmp_path, 10)
        seen: list[tuple[int, int]] = []
        lock = threading.Lock()

        def on_progress(processed, total):
            with lock:
                seen.append((processed, total))

        indexer.full_reindex(base_path=str(tmp_path), source="obsidian", on_progress=on_progress)

        assert seen, "progress callback was never invoked"
        assert all(total == 10 for _, total in seen)
        assert max(p for p, _ in seen) == 10

    def test_wikilinks_resolve_after_parallel_index(self, indexer, tmp_path):
        _write_vault(tmp_path, 8)

        indexer.full_reindex(base_path=str(tmp_path), source="obsidian")

        # The link graph must be populated correctly despite concurrent updates.
        assert indexer.link_graph.resolve("note_0") == "note_0.md"
        neighbors = indexer.link_graph.neighbors("note_7.md", max_degree=1)
        assert "note_0.md" in neighbors

    def test_serial_and_parallel_produce_same_index(self, indexer, tmp_path):
        _write_vault(tmp_path, 9)

        with patch("rag_api.indexer.OBSIDIAN_REINDEX_WORKERS", 1):
            indexer.full_reindex(base_path=str(tmp_path), source="obsidian")
        serial_ids = set(indexer.collection.get()["ids"])

        # Re-index with concurrency; unchanged files are skipped, so force a
        # rebuild by clearing hashes first.
        indexer._file_hashes.clear()
        with patch("rag_api.indexer.OBSIDIAN_REINDEX_WORKERS", 8):
            indexer.full_reindex(base_path=str(tmp_path), source="obsidian")
        parallel_ids = set(indexer.collection.get()["ids"])

        assert serial_ids == parallel_ids


class TestLinkGraphThreadSafety:
    def test_concurrent_mutations_do_not_corrupt(self):
        from rag_api.graph import LinkGraph

        graph = LinkGraph()
        n = 200

        def worker(i: int) -> None:
            path = f"dir/note_{i}.md"
            graph.register(path)
            graph.update(path, ["Note 0"] if i else [])
            graph.update_tags(path, [f"tag{i % 5}"])
            graph.resolve(f"note_{i}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(n):
            assert graph.resolve(f"note_{i}") == f"dir/note_{i}.md"
        # Files sharing a tag are discoverable via tag_neighbors.
        assert graph.tag_neighbors("dir/note_0.md")

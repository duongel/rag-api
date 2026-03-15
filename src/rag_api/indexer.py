"""Indexer: manages the ChromaDB collection and incremental updates."""

import hashlib
import logging
from pathlib import Path

import chromadb

from .config import VAULT_PATH, CHROMA_PATH
from .graph import LinkGraph
from .parser import parse_markdown, parse_pdf, extract_wikilinks, extract_tags

from .embeddings import embed_documents

logger = logging.getLogger(__name__)

_EMBED_BATCH = 64


class Indexer:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(
            name="rag_documents",
            metadata={"hnsw:space": "cosine"},
        )
        self._file_hashes: dict[str, str] = {}
        self.link_graph = LinkGraph()
        self._load_file_hashes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file_hashes(self):
        """Bootstrap ``_file_hashes`` from existing collection metadata."""
        try:
            results = self.collection.get(include=["metadatas"])
            for meta in results["metadatas"] or []:
                fp = meta.get("file_path")
                fh = meta.get("file_hash")
                if fp and fh:
                    self._file_hashes[fp] = fh
        except Exception:
            pass

    @staticmethod
    def _file_content_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(self, file_path: str) -> bool:
        """Index / re-index a single Markdown or PDF file."""
        full_path = Path(VAULT_PATH) / file_path
        suffix = full_path.suffix.lower()

        if not full_path.exists() or suffix not in (".md", ".pdf"):
            return False

        # Always register for wikilink resolution (cheap, idempotent)
        self.link_graph.register(file_path)

        file_hash = self._file_content_hash(full_path)
        if self._file_hashes.get(file_path) == file_hash:
            return False  # nothing changed

        self.remove_file(file_path)

        if suffix == ".md":
            # Update link graph from raw content (before wikilink replacement)
            try:
                raw = full_path.read_text(encoding="utf-8", errors="ignore")
                self.link_graph.update(file_path, extract_wikilinks(raw))
                self.link_graph.update_tags(file_path, extract_tags(raw))
            except Exception:
                pass
            chunks = parse_markdown(file_path, VAULT_PATH)
        else:  # .pdf
            chunks = parse_pdf(file_path, VAULT_PATH)

        if not chunks:
            return False

        texts = [c.content for c in chunks]
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            embeddings.extend(embed_documents(texts[i : i + _EMBED_BATCH]))

        ids = [f"{file_path}#chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_path": file_path,
                "section": c.section,
                "file_hash": file_hash,
                "chunk_index": i,
            }
            for i, c in enumerate(chunks)
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        self._file_hashes[file_path] = file_hash
        logger.info("Indexed %s (%d chunks)", file_path, len(chunks))
        return True

    def remove_file(self, file_path: str):
        """Remove all chunks belonging to *file_path* from the index."""
        try:
            self.collection.delete(where={"file_path": file_path})
        except Exception:
            pass
        self._file_hashes.pop(file_path, None)
        self.link_graph.remove(file_path)

    def full_reindex(self, on_progress=None) -> int:
        """Walk the entire vault and index every ``.md`` and ``.pdf`` file.

        *on_progress(processed, total)* is called after each file so callers
        can track live progress. Returns the number of files actually updated.
        """
        vault = Path(VAULT_PATH)
        count = 0

        def _is_hidden(rel: Path) -> bool:
            return any(p.startswith(".") for p in rel.parts)

        # Pass 1: register all .md files so wikilinks resolve correctly
        for md_file in vault.rglob("*.md"):
            rel = md_file.relative_to(vault)
            if not _is_hidden(rel):
                self.link_graph.register(str(rel))

        # Collect full file list upfront so we know the total
        all_files = [
            f
            for f in sorted(vault.rglob("*.md")) + sorted(vault.rglob("*.pdf"))
            if not _is_hidden(f.relative_to(vault))
        ]
        total = len(all_files)

        for processed, file_path in enumerate(all_files, start=1):
            rel_path = str(file_path.relative_to(vault))
            try:
                if self.index_file(rel_path):
                    count += 1
            except Exception as e:
                logger.error("Error indexing %s: %s", rel_path, e)

            if on_progress:
                on_progress(processed, total)

        self._cleanup_deleted()
        logger.info("Full reindex complete – %d files updated.", count)
        return count

    def _cleanup_deleted(self):
        """Remove index entries whose source file no longer exists."""
        vault = Path(VAULT_PATH)
        for fp in list(self._file_hashes):
            if not (vault / fp).exists():
                self.remove_file(fp)
                logger.info("Removed deleted file from index: %s", fp)

    def get_stats(self) -> dict:
        return {
            "total_chunks": self.collection.count(),
            "total_files": len(self._file_hashes),
            "link_graph_edges": len(self.link_graph),
        }

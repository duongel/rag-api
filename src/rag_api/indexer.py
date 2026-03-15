"""Indexer: manages the ChromaDB collection and incremental updates."""

import hashlib
import logging
from pathlib import Path

import chromadb

from .config import VAULT_PATH, CHROMA_PATH, PAPERLESS_ARCHIVE_PATH
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
        # Maps file_path key → source ("obsidian" | "paperless")
        self._file_sources: dict[str, str] = {}
        self.link_graph = LinkGraph()
        self._load_file_hashes()

    @staticmethod
    def _doc_key(source: str, file_path: str) -> str:
        return f"{source}::{file_path}"

    @staticmethod
    def _file_path_from_key(doc_key: str) -> str:
        return doc_key.split("::", 1)[1]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file_hashes(self):
        """Bootstrap ``_file_hashes`` and ``_file_sources`` from existing collection metadata."""
        try:
            results = self.collection.get(include=["metadatas"])
            for meta in results["metadatas"] or []:
                fp = meta.get("file_path")
                fh = meta.get("file_hash")
                source = meta.get("source", "obsidian")
                if fp and fh:
                    doc_key = self._doc_key(source, fp)
                    self._file_hashes[doc_key] = fh
                    self._file_sources[doc_key] = source
        except Exception:
            pass

    @staticmethod
    def _file_content_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _base_path_for_source(self, source: str) -> str:
        if source == "paperless":
            return PAPERLESS_ARCHIVE_PATH
        return VAULT_PATH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(self, file_path: str, base_path: str | None = None, source: str = "obsidian") -> bool:
        """Index / re-index a single Markdown or PDF file.

        *base_path* defaults to ``VAULT_PATH`` for obsidian files.
        *source* is stored as metadata and used to route cleanup and keyword search.
        """
        resolved_base = base_path or VAULT_PATH
        full_path = Path(resolved_base) / file_path
        suffix = full_path.suffix.lower()

        if not full_path.exists() or suffix not in (".md", ".pdf"):
            return False

        # Always register for wikilink resolution (cheap, idempotent)
        if source == "obsidian":
            self.link_graph.register(file_path)

        doc_key = self._doc_key(source, file_path)
        file_hash = self._file_content_hash(full_path)
        if self._file_hashes.get(doc_key) == file_hash:
            return False  # nothing changed

        self.remove_file(file_path, source=source)

        extra_meta: dict = {}
        if suffix == ".md":
            # Update link graph from raw content (before wikilink replacement)
            try:
                raw = full_path.read_text(encoding="utf-8", errors="ignore")
                self.link_graph.update(file_path, extract_wikilinks(raw))
                self.link_graph.update_tags(file_path, extract_tags(raw))
            except Exception:
                pass
            chunks = parse_markdown(file_path, resolved_base)
        else:  # .pdf
            extra_meta = _paperless_api_meta(file_path) if source == "paperless" else {}
            chunks = parse_pdf(file_path, resolved_base)

        if not chunks:
            return False

        texts = [c.content for c in chunks]
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            embeddings.extend(embed_documents(texts[i : i + _EMBED_BATCH]))

        ids = [f"{source}::{file_path}#chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_path": file_path,
                "section": c.section,
                "file_hash": file_hash,
                "chunk_index": i,
                "source": source,
                **extra_meta,
            }
            for i, c in enumerate(chunks)
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        self._file_hashes[doc_key] = file_hash
        self._file_sources[doc_key] = source
        logger.info("Indexed %s [%s] (%d chunks)", file_path, source, len(chunks))
        return True

    def remove_file(self, file_path: str, source: str = "obsidian"):
        """Remove all chunks belonging to *file_path* from the index."""
        doc_key = self._doc_key(source, file_path)
        try:
            # Current-style chunks: have an explicit source field.
            self.collection.delete(where={"file_path": file_path, "source": source})
        except Exception:
            pass
        try:
            # Legacy chunks (pre-source schema): no source field stored.
            # Fetch by file_path, then delete only IDs that lack a source field
            # to avoid accidentally removing same-path chunks from the other source.
            results = self.collection.get(
                where={"file_path": {"$eq": file_path}},
                include=["metadatas"],
            )
            legacy_ids = [
                id_
                for id_, meta in zip(results["ids"], results["metadatas"])
                if "source" not in meta
            ]
            if legacy_ids:
                self.collection.delete(ids=legacy_ids)
        except Exception:
            pass
        self._file_hashes.pop(doc_key, None)
        self._file_sources.pop(doc_key, None)
        if source == "obsidian":
            self.link_graph.remove(file_path)

    def full_reindex(self, base_path: str | None = None, source: str = "obsidian", on_progress=None) -> int:
        """Walk *base_path* (default: VAULT_PATH) and index every ``.md`` and ``.pdf`` file.

        *on_progress(processed, total)* is called after each file so callers
        can track live progress. Returns the number of files actually updated.
        """
        root = Path(base_path or VAULT_PATH)
        count = 0

        if not root.exists():
            logger.warning(
                "Skipping full reindex for source '%s': base path does not exist (%s)",
                source,
                root,
            )
            return 0

        def _is_hidden(rel: Path) -> bool:
            return any(p.startswith(".") for p in rel.parts)

        if source == "obsidian":
            # Pass 1: register all .md files so wikilinks resolve correctly
            for md_file in root.rglob("*.md"):
                rel = md_file.relative_to(root)
                if not _is_hidden(rel):
                    self.link_graph.register(str(rel))

            all_files = [
                f
                for f in sorted(root.rglob("*.md")) + sorted(root.rglob("*.pdf"))
                if not _is_hidden(f.relative_to(root))
            ]
        else:
            # Paperless archive: PDFs only, no hidden-dir filtering needed
            all_files = sorted(root.rglob("*.pdf"))

        total = len(all_files)

        for processed, file_path in enumerate(all_files, start=1):
            rel_path = str(file_path.relative_to(root))
            try:
                if self.index_file(rel_path, base_path=str(root), source=source):
                    count += 1
            except Exception as e:
                logger.error("Error indexing %s: %s", rel_path, e)

            if on_progress:
                on_progress(processed, total)

        self._cleanup_deleted(source=source, base_path=str(root))
        logger.info("Full reindex [%s] complete – %d files updated.", source, count)
        return count

    def _cleanup_deleted(self, source: str = "obsidian", base_path: str | None = None):
        """Remove index entries whose source file no longer exists."""
        root = Path(base_path or self._base_path_for_source(source))
        for doc_key in list(self._file_hashes):
            if self._file_sources.get(doc_key, "obsidian") != source:
                continue
            fp = self._file_path_from_key(doc_key)
            if not (root / fp).exists():
                self.remove_file(fp, source=source)
                logger.info("Removed deleted file from index: %s", fp)

    def get_stats(self) -> dict:
        paperless_count = sum(1 for s in self._file_sources.values() if s == "paperless")
        return {
            "total_chunks": self.collection.count(),
            "total_files": len(self._file_hashes),
            "obsidian_files": len(self._file_hashes) - paperless_count,
            "paperless_files": paperless_count,
            "link_graph_edges": len(self.link_graph),
        }


# ---------------------------------------------------------------------------
# Optional Paperless API metadata enrichment
# ---------------------------------------------------------------------------

def _paperless_api_meta(file_path: str) -> dict:
    """Fetch document metadata from the Paperless REST API.

    Called only when PAPERLESS_URL and PAPERLESS_TOKEN are configured.
    Returns a dict with title/tags/correspondent keys, or {} on any failure.

    Paperless archive filenames follow the pattern ``<pk>.pdf`` (or a custom
    naming scheme). We derive the document ID from the stem and query the API.
    """
    from .config import PAPERLESS_URL, PAPERLESS_TOKEN
    if not PAPERLESS_URL or not PAPERLESS_TOKEN:
        return {}

    stem = Path(file_path).stem
    if not stem.isdigit():
        return {}

    import requests
    try:
        resp = requests.get(
            f"{PAPERLESS_URL}/api/documents/{stem}/",
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
            timeout=5,
        )
        if not resp.ok:
            return {}
        data = resp.json()
        meta: dict = {}
        if data.get("title"):
            meta["title"] = data["title"]
        if data.get("correspondent"):
            meta["correspondent"] = str(data["correspondent"])
        tags = data.get("tags", [])
        if tags:
            meta["tags"] = ",".join(str(t) for t in tags)
        if data.get("created"):
            meta["created"] = data["created"]
        return meta
    except Exception:
        return {}

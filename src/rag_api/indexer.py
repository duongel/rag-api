"""Indexer: manages the ChromaDB collection and incremental updates."""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Sequence, Union

import chromadb

from .config import VAULT_PATH, CHROMA_PATH
from .graph import LinkGraph
from .parser import parse_markdown, parse_pdf, parse_plaintext, extract_wikilinks, extract_tags

from .embeddings import embed_documents

logger = logging.getLogger(__name__)

_EMBED_BATCH = 64
_PAPERLESS_TAG_NAME_CACHE: dict[str, str] = {}


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
        # Tracks API document signatures (content + indexed metadata) for Paperless docs
        self._api_content_hashes: dict[str, str] = {}
        # Maps paperless doc_id (str) → currently indexed file_path for O(1) rename detection
        self._paperless_doc_paths: dict[str, str] = {}
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
        """Bootstrap ``_file_hashes``, ``_file_sources``, and ``_api_content_hashes`` from existing collection metadata."""
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
                    ach = meta.get("api_content_hash")
                    if ach:
                        self._api_content_hashes[doc_key] = ach
                    pdid = meta.get("paperless_doc_id")
                    if pdid and source == "paperless":
                        self._paperless_doc_paths[pdid] = fp
        except Exception:
            pass

    @staticmethod
    def _file_content_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _base_path_for_source(self, source: str) -> str:
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
            chunks = parse_pdf(file_path, resolved_base)

        if not chunks:
            return False

        if source == "paperless" and extra_meta:
            texts = [_with_paperless_metadata_text(c.content, extra_meta) for c in chunks]
        else:
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

    def index_paperless_doc(self, doc: dict) -> bool:
        """Index a single Paperless document from its API data.

        *doc* is a full document dict from the Paperless ``/api/documents/`` endpoint.
        Returns True if the document was (re-)indexed, False if unchanged.
        """
        doc_id = doc.get("id")
        if doc_id is None:
            return False

        content = (doc.get("content") or "").strip()
        if not content:
            # Only remove if the payload actually included a content field;
            # list responses may omit content entirely.
            if "content" in doc:
                self._remove_all_paths_for_paperless_doc(doc_id)
            return False

        # Use archive_filename as file_path when available, otherwise synthesize
        file_path = doc.get("archive_filename") or f"paperless/{doc_id}.pdf"
        doc_key = self._doc_key("paperless", file_path)

        meta: dict = {"paperless_doc_id": str(doc_id)}
        if doc.get("title"):
            meta["title"] = doc["title"]
        if doc.get("correspondent"):
            meta["correspondent"] = str(doc["correspondent"])
        tags = doc.get("tags", [])
        if tags:
            meta["tags"] = ",".join(str(t) for t in tags)
            from .config import PAPERLESS_URL, PAPERLESS_TOKEN
            if PAPERLESS_URL and PAPERLESS_TOKEN:
                tag_names = _paperless_tag_names(tags, PAPERLESS_URL, PAPERLESS_TOKEN)
                if tag_names:
                    meta["tag_names"] = ", ".join(tag_names)
        if doc.get("created"):
            meta["created"] = doc["created"]

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        api_doc_hash = hashlib.sha256(
            json.dumps(
                {
                    "content": content,
                    "title": meta.get("title"),
                    "correspondent": meta.get("correspondent"),
                    "tags": meta.get("tags"),
                    "created": meta.get("created"),
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        # O(1) rename detection: check if this doc_id was previously indexed under a different path
        prev_path = self._paperless_doc_paths.get(str(doc_id))
        path_changed = prev_path is not None and prev_path != file_path

        if not path_changed and self._api_content_hashes.get(doc_key) == api_doc_hash:
            return False  # unchanged

        # Remove all existing entries for this doc ID (handles renamed archive files)
        self._remove_all_paths_for_paperless_doc(doc_id)
        self.remove_file(file_path, source="paperless")

        chunks = parse_plaintext(file_path, content)
        if not chunks:
            return False

        texts = [_with_paperless_metadata_text(c.content, meta) for c in chunks]
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            embeddings.extend(embed_documents(texts[i : i + _EMBED_BATCH]))

        ids = [f"paperless::{file_path}#chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_path": file_path,
                "section": c.section,
                "file_hash": content_hash,
                "chunk_index": i,
                "source": "paperless",
                "api_content_hash": api_doc_hash,
                **meta,
            }
            for i, c in enumerate(chunks)
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        self._file_hashes[doc_key] = content_hash
        self._file_sources[doc_key] = "paperless"
        self._api_content_hashes[doc_key] = api_doc_hash
        self._paperless_doc_paths[str(doc_id)] = file_path
        logger.info("Indexed paperless doc %s [%s] (%d chunks)", doc_id, file_path, len(chunks))
        return True

    def remove_file(self, file_path: str, source: str = "obsidian"):
        """Remove all chunks belonging to *file_path* from the index."""
        doc_key = self._doc_key(source, file_path)
        try:
            # Current-style chunks: have an explicit source field.
            self.collection.delete(where={"$and": [{"file_path": file_path}, {"source": source}]})
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
        self._api_content_hashes.pop(doc_key, None)
        if source == "obsidian":
            self.link_graph.remove(file_path)

    def full_reindex(self, base_path: str | None = None, source: str = "obsidian", on_progress=None) -> int:
        """Walk *base_path* (default: VAULT_PATH) and index every ``.md`` and ``.pdf`` file.

        For ``source="paperless"`` with ``PAPERLESS_URL`` configured, fetches
        all documents from the Paperless REST API instead of scanning the file
        system.  This finds *all* documents (including those without an archive
        version) and avoids N+1 HTTP requests.

        *on_progress(processed, total)* is called after each file so callers
        can track live progress. Returns the number of files actually updated.
        """
        if source == "paperless":
            return self._reindex_paperless_api(on_progress)

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

        total = len(all_files)

        if on_progress:
            on_progress(0, total)

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

    def _reindex_paperless_api(self, on_progress=None) -> int:
        """Fetch all Paperless documents via the REST API and index them.

        Replaces the filesystem-based reindex with ~38 paginated API calls
        (page_size=100) that cover *all* documents, including those without
        an archive version.
        """
        from .config import PAPERLESS_URL, PAPERLESS_TOKEN
        if not PAPERLESS_URL or not PAPERLESS_TOKEN:
            logger.warning("Paperless API not configured — skipping reindex")
            return 0

        import requests
        headers = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

        # Phase 1: collect all documents from the API
        all_docs: list[dict] = []
        page = 1
        fetch_complete = False
        while True:
            try:
                resp = requests.get(
                    f"{PAPERLESS_URL}/api/documents/",
                    params={
                        "page": page,
                        "page_size": 100,
                        "fields": "id,content,archive_filename,title,correspondent,tags,created",
                    },
                    headers=headers,
                    timeout=30,
                )
            except Exception as e:
                logger.error("Paperless API request failed: %s", e)
                break
            if not resp.ok:
                logger.error("Paperless API returned %d", resp.status_code)
                break
            data = resp.json()
            all_docs.extend(data.get("results", []))
            if not data.get("next"):
                fetch_complete = True
                break
            page += 1

        if not all_docs and not fetch_complete:
            logger.warning("No documents returned from Paperless API (fetch incomplete)")
            return 0

        logger.info("Fetched %d documents from Paperless API (%d pages)", len(all_docs), page)
        total = len(all_docs)

        if on_progress:
            on_progress(0, total)

        # Phase 2: index each document
        count = 0
        indexed_file_paths: set[str] = set()
        for processed, doc in enumerate(all_docs, start=1):
            try:
                # List responses may omit content; fetch individual doc details.
                if "content" not in doc and doc.get("id") is not None:
                    try:
                        detail = requests.get(
                            f"{PAPERLESS_URL}/api/documents/{doc['id']}/",
                            headers=headers,
                            timeout=10,
                        )
                        if detail.ok:
                            doc = detail.json()
                    except Exception as e:
                        logger.warning("Failed to fetch detail for doc %s: %s", doc["id"], e)
                # Track the file path that will actually be used for indexing
                fp = doc.get("archive_filename") or f"paperless/{doc.get('id')}.pdf"
                indexed_file_paths.add(fp)
                if self.index_paperless_doc(doc):
                    count += 1
            except Exception as e:
                logger.error("Error indexing paperless doc %s: %s", doc.get("id"), e)

            if on_progress:
                on_progress(processed, total)

        # Phase 3: remove documents no longer in Paperless
        # Only run cleanup when all pages were fetched successfully;
        # a partial fetch would incorrectly delete still-existing docs.
        if fetch_complete:
            for doc_key in list(self._file_hashes):
                if self._file_sources.get(doc_key, "obsidian") != "paperless":
                    continue
                fp = self._file_path_from_key(doc_key)
                if fp not in indexed_file_paths:
                    self.remove_file(fp, source="paperless")
                    logger.info("Removed deleted paperless doc from index: %s", fp)
        else:
            logger.warning("Skipping cleanup — API fetch was incomplete (%d pages, %d docs)", page, len(all_docs))

        logger.info("Full reindex [paperless] complete – %d docs updated.", count)
        return count

    def reindex_paperless_doc(self, doc_id: int) -> bool:
        """Re-index a single Paperless document by its ID.

        Called by the webhook endpoint when Paperless notifies about a change.
        """
        from .config import PAPERLESS_URL, PAPERLESS_TOKEN
        if not PAPERLESS_URL or not PAPERLESS_TOKEN:
            return False

        import requests
        headers = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

        try:
            resp = requests.get(
                f"{PAPERLESS_URL}/api/documents/{doc_id}/",
                headers=headers,
                timeout=10,
            )
            if not resp.ok:
                raise RuntimeError(f"Paperless doc {doc_id} not found (HTTP {resp.status_code})")
            return self.index_paperless_doc(resp.json())
        except Exception:
            logger.exception("Failed to fetch/index paperless doc %d", doc_id)
            raise

    def remove_paperless_doc(self, doc_id: int):
        """Remove a Paperless document from the index by its ID."""
        # Collect all file paths for this doc (synthetic path + metadata matches)
        paths_to_remove: set[str] = set()

        synthetic = f"paperless/{doc_id}.pdf"
        if self._doc_key("paperless", synthetic) in self._file_hashes:
            paths_to_remove.add(synthetic)

        for doc_key in list(self._file_hashes):
            if self._file_sources.get(doc_key, "obsidian") != "paperless":
                continue
            fp = self._file_path_from_key(doc_key)
            if fp == synthetic:
                paths_to_remove.add(fp)

        try:
            results = self.collection.get(
                where={"paperless_doc_id": str(doc_id)},
                include=["metadatas"],
            )
            if results["ids"]:
                for m in results["metadatas"]:
                    fp = m.get("file_path", "")
                    if fp:
                        paths_to_remove.add(fp)
        except Exception:
            pass

        self._paperless_doc_paths.pop(str(doc_id), None)
        for fp in paths_to_remove:
            self.remove_file(fp, source="paperless")

    def _remove_all_paths_for_paperless_doc(self, doc_id: int):
        """Remove all indexed paths associated with a Paperless document ID."""
        self._paperless_doc_paths.pop(str(doc_id), None)
        try:
            results = self.collection.get(
                where={"paperless_doc_id": str(doc_id)},
                include=["metadatas"],
            )
            if results["ids"]:
                for m in results["metadatas"]:
                    fp = m.get("file_path", "")
                    if fp:
                        self.remove_file(fp, source="paperless")
        except Exception:
            pass

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

def _with_paperless_metadata_text(content: str, meta: dict) -> str:
    """Prefix chunk text with human-readable Paperless metadata when present.

    This lets semantic + keyword retrieval match tags/title/correspondent even
    if these terms do not appear in the OCR-extracted PDF body.
    """
    lines: list[str] = []
    if meta.get("title"):
        lines.append(f"Title: {meta['title']}")
    if meta.get("correspondent"):
        lines.append(f"Correspondent: {meta['correspondent']}")
    if meta.get("tag_names"):
        lines.append(f"Tags: {meta['tag_names']}")
    elif meta.get("tags"):
        lines.append(f"Tags: {meta['tags']}")
    if not lines:
        return content
    return "Paperless Metadata\n" + "\n".join(lines) + "\n\n" + content


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
            tag_names = _paperless_tag_names(tags, PAPERLESS_URL, PAPERLESS_TOKEN)
            if tag_names:
                meta["tag_names"] = ", ".join(tag_names)
        if data.get("created"):
            meta["created"] = data["created"]
        return meta
    except Exception:
        return {}


def _paperless_tag_names(
    tag_ids: Sequence[Union[int, str]], paperless_url: str, token: str
) -> List[str]:
    """Resolve Paperless tag IDs to names with an in-memory cache."""
    import requests

    names: list[str] = []
    for raw_tag_id in tag_ids:
        tag_id = str(raw_tag_id)
        if tag_id in _PAPERLESS_TAG_NAME_CACHE:
            cached = _PAPERLESS_TAG_NAME_CACHE[tag_id]
            if cached:
                names.append(cached)
            continue

        try:
            resp = requests.get(
                f"{paperless_url}/api/tags/{tag_id}/",
                headers={"Authorization": f"Token {token}"},
                timeout=5,
            )
            if not resp.ok:
                continue
            name = str(resp.json().get("name", "")).strip()
            if name:
                _PAPERLESS_TAG_NAME_CACHE[tag_id] = name
                names.append(name)
        except Exception:
            continue

    return names

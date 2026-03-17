"""Semantic and keyword search across the indexed Obsidian vault."""

import logging
import re
from pathlib import Path
from typing import Optional

from .config import VAULT_PATH, DATA_SOURCES
from .embeddings import embed_query
from .indexer import Indexer

logger = logging.getLogger(__name__)

# Maximum number of link-expanded notes appended to a result set
_MAX_LINK_EXPANSIONS = 10

# How much of the source result's semantic score is added to a connected note's score.
# Higher = connection type matters more in the final ranking.
_BOOST_FACTOR: dict[str, float] = {
    "link_1":   0.30,   # direct outgoing wikilink
    "backlink": 0.25,   # another note links TO the result
    "tag":      0.20,   # shared tag
    "link_2":   0.10,   # second-degree outgoing wikilink
}

# Tiebreak when a file is reachable via multiple connection types
_PRIORITY: dict[str, int] = {
    "link_1": 0, "backlink": 1, "tag": 2, "link_2": 3,
}


class Searcher:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self.collection = indexer.collection

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def semantic_search(
        self, query: str, top_k: int = 5, expand_links: bool = True,
        paperless_doc_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Embed *query*, return the most similar chunks, and optionally
        append linked notes up to 2 degrees of separation.

        When *paperless_doc_ids* is given, only chunks belonging to those
        Paperless documents are searched (pre-filter).
        """
        query_embedding = embed_query(query)

        where = None
        if paperless_doc_ids is not None:
            if not paperless_doc_ids:
                return []  # filter matched nothing
            if len(paperless_doc_ids) == 1:
                where = {"paperless_doc_id": paperless_doc_ids[0]}
            else:
                where = {"paperless_doc_id": {"$in": paperless_doc_ids}}

        query_kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self.collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = self.collection.query(**query_kwargs)

        output: list[dict] = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            entry: dict = {
                "file_path": meta["file_path"],
                "section": meta.get("section", ""),
                "content": results["documents"][0][i],
                "score": round(1 - results["distances"][0][i], 4),
                "match_type": "semantic",
                "source": meta.get("source", "obsidian"),
            }
            if meta.get("paperless_doc_id"):
                entry["paperless_doc_id"] = meta["paperless_doc_id"]
            output.append(entry)

        if expand_links:
            output = self._expand_with_links(output, query_embedding, top_k)

        return output[:top_k]

    # ------------------------------------------------------------------
    # Link-graph expansion
    # ------------------------------------------------------------------

    def _expand_with_links(
        self, results: list[dict], query_embedding: list[float], top_k: int
    ) -> list[dict]:
        """Graph-boosted ranking:

        1. Collect candidate files via outgoing links, backlinks, tags (up to
           2 link degrees).
        2. For each candidate accumulate a *boost* = Σ source_score × factor
           across every semantic result that is graph-connected to it.
        3. Fetch the semantically closest chunk for each candidate and add the
           accumulated boost to its raw score.
        4. Merge semantic results + boosted candidates and sort by final score.

        This means a linked note with a modest semantic score can rank above a
        weakly matching semantic result when it is strongly connected.
        """
        lg = getattr(self.indexer, "link_graph", None)
        if lg is None:
            return results

        # Give already-semantic hits a small graph bonus too, so the final
        # ranking is truly graph-aware instead of only boosting newly added files.
        seed_results = [dict(result) for result in results]
        for result in results:
            result["score"] = round(
                result["score"] + self._graph_bonus_for_file(result["file_path"], seed_results),
                4,
            )

        seen_files: set[str] = {r["file_path"] for r in results}
        # fp → {"mt": best_connection_type, "boost": accumulated_boost}
        candidates: dict[str, dict] = {}

        for result in results:
            fp0, src_score = result["file_path"], result["score"]

            connections: list[tuple[str, str]] = []
            for fp, degree in lg.neighbors(fp0, max_degree=2).items():
                connections.append((fp, f"link_{degree}"))
            for fp in lg.backlink_neighbors(fp0):
                connections.append((fp, "backlink"))
            for fp in lg.tag_neighbors(fp0):
                connections.append((fp, "tag"))

            for fp, mt in connections:
                if fp in seen_files:
                    continue
                contrib = src_score * _BOOST_FACTOR.get(mt, 0)
                if fp not in candidates:
                    candidates[fp] = {"mt": mt, "boost": contrib}
                else:
                    # Keep the highest-priority connection type; always sum boost
                    if _PRIORITY.get(mt, 99) < _PRIORITY.get(candidates[fp]["mt"], 99):
                        candidates[fp]["mt"] = mt
                    candidates[fp]["boost"] += contrib

        if not candidates:
            return results

        # Sort by accumulated boost, keep top N
        top = sorted(candidates.items(), key=lambda x: x[1]["boost"], reverse=True)[
            : min(_MAX_LINK_EXPANSIONS, max(top_k, 0))
        ]

        extra: list[dict] = []
        for fp, info in top:
            chunk = self._best_chunk_for_file(fp, query_embedding)
            if chunk:
                chunk["match_type"] = info["mt"]
                chunk["score"] = round(chunk["score"] + info["boost"], 4)
                extra.append(chunk)

        # Merge and re-rank: best score wins regardless of origin
        merged = results + extra
        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged

    def _graph_bonus_for_file(self, file_path: str, seed_results: list[dict]) -> float:
        """Return a small accumulated graph bonus for an already-ranked file."""
        lg = getattr(self.indexer, "link_graph", None)
        if lg is None:
            return 0.0

        bonus = 0.0
        for result in seed_results:
            src_file = result["file_path"]
            if src_file == file_path:
                continue

            neighbors = lg.neighbors(src_file, max_degree=2)
            if file_path in neighbors:
                bonus += result["score"] * _BOOST_FACTOR.get(f"link_{neighbors[file_path]}", 0)

            if file_path in lg.backlink_neighbors(src_file):
                bonus += result["score"] * _BOOST_FACTOR["backlink"]

            if file_path in lg.tag_neighbors(src_file):
                bonus += result["score"] * _BOOST_FACTOR["tag"]

        return bonus

    def _best_chunk_for_file(
        self, file_path: str, query_embedding: list[float]
    ) -> dict | None:
        """Return the semantically closest chunk for a specific file."""
        try:
            res = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                where={"file_path": file_path},
                include=["documents", "metadatas", "distances"],
            )
            if res["ids"][0]:
                meta = res["metadatas"][0][0]
                entry: dict = {
                    "file_path": meta["file_path"],
                    "section": meta.get("section", ""),
                    "content": res["documents"][0][0],
                    "score": round(1 - res["distances"][0][0], 4),
                    "source": meta.get("source", "obsidian"),
                }
                if meta.get("paperless_doc_id"):
                    entry["paperless_doc_id"] = meta["paperless_doc_id"]
                return entry
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Keyword / exact-match search
    # ------------------------------------------------------------------

    def keyword_search(
        self, query: str, top_k: int = 10,
        paperless_doc_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search filenames and document content for *query* (case-insensitive).

        Scoring is based on match location, word-boundary matches, and
        frequency so that results containing the query more often or as a
        whole word rank higher.

        When *paperless_doc_ids* is given, only Paperless documents with
        those IDs are considered.
        """
        allowed_doc_ids: Optional[set[str]] = None
        if paperless_doc_ids is not None:
            if not paperless_doc_ids:
                return []
            allowed_doc_ids = set(paperless_doc_ids)

        query_lower = query.lower()
        word_pattern = re.compile(r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE)
        results: list[dict] = []
        seen: set[str] = set()

        # 1) Filename matches — only for text-readable (Markdown) obsidian files
        for doc_key, source in self.indexer._file_sources.items():
            fp = self.indexer._file_path_from_key(doc_key)
            if query_lower not in fp.lower():
                continue
            # When Paperless filters are active, skip non-matching files
            if allowed_doc_ids is not None and source != "paperless":
                continue
            if source == "paperless" or not fp.endswith(".md"):
                # PDFs are binary; content is already in ChromaDB (step 2)
                results.append(
                    {
                        "file_path": fp,
                        "section": "",
                        "content": "",
                        "score": 1.0,
                        "match_type": "filename",
                        "source": source,
                    }
                )
                seen.add(f"{source}::{fp}")
                continue
            base = Path(VAULT_PATH)
            full_path = base / fp
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                results.append(
                    {
                        "file_path": fp,
                        "section": "",
                        "content": content[:1000],
                        "score": 1.0,
                        "match_type": "filename",
                        "source": source,
                    }
                )
                seen.add(f"{source}::{fp}")

        # 2) Content matches — always case-insensitive via full scan
        try:
            get_kwargs: dict = {"include": ["documents", "metadatas"]}
            if allowed_doc_ids is not None:
                if len(allowed_doc_ids) == 1:
                    get_kwargs["where"] = {"paperless_doc_id": next(iter(allowed_doc_ids))}
                else:
                    get_kwargs["where"] = {"paperless_doc_id": {"$in": list(allowed_doc_ids)}}
            all_docs = self.collection.get(**get_kwargs)
            for i, doc in enumerate(all_docs["documents"] or []):
                if query_lower not in doc.lower():
                    continue
                meta = all_docs["metadatas"][i]
                key = f"{meta.get('source', 'obsidian')}::{meta['file_path']}#{meta.get('section', '')}"
                if key in seen:
                    continue
                score = self._keyword_score(doc, query_lower, word_pattern)
                entry: dict = {
                    "file_path": meta["file_path"],
                    "section": meta.get("section", ""),
                    "content": doc[:1000],
                    "score": score,
                    "match_type": "content",
                    "source": meta.get("source", "obsidian"),
                }
                if meta.get("paperless_doc_id"):
                    entry["paperless_doc_id"] = meta["paperless_doc_id"]
                results.append(entry)
                seen.add(key)
        except Exception:
            pass


        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    @staticmethod
    def _keyword_score(
        doc: str, query_lower: str, word_pattern: re.Pattern[str]
    ) -> float:
        """Compute a relevance score for a keyword match.

        Base score is 0.70.  Bonuses:
        - frequency:  +0.03 per occurrence (max +0.15)
        - whole-word: +0.05 if at least one word-boundary match
        - position:   +0.05 if first hit is in the first 20 % of the chunk
        """
        doc_lower = doc.lower()
        count = doc_lower.count(query_lower)
        freq_bonus = min(count * 0.03, 0.15)
        word_bonus = 0.05 if word_pattern.search(doc) else 0.0
        pos = doc_lower.find(query_lower)
        pos_bonus = 0.05 if pos >= 0 and pos < len(doc) * 0.2 else 0.0
        return round(0.70 + freq_bonus + word_bonus + pos_bonus, 4)

    # ------------------------------------------------------------------
    # Single note retrieval
    # ------------------------------------------------------------------

    def get_note(self, path: str) -> dict | None:
        """Return full content of a note by relative path.

        For Obsidian notes the file is read from disk.  For Paperless
        documents (or any file not on disk) the content is reassembled
        from the chunks stored in ChromaDB.
        """
        # Try the Obsidian vault first
        if DATA_SOURCES != "paperless":
            full_path = Path(VAULT_PATH) / path
            if full_path.exists():
                return {
                    "file_path": path,
                    "content": full_path.read_text(encoding="utf-8"),
                }

        # Fall back to ChromaDB (covers Paperless and any indexed-only docs)
        return self._get_note_from_index(path)

    def _get_note_from_index(self, path: str) -> dict | None:
        """Reassemble a document's content from its indexed chunks."""
        try:
            results = self.collection.get(
                where={"file_path": path},
                include=["documents", "metadatas"],
            )
        except Exception:
            return None

        if not results["ids"]:
            return None

        # Sort chunks by chunk_index to restore original order
        pairs = sorted(
            zip(results["metadatas"], results["documents"]),
            key=lambda p: p[0].get("chunk_index", 0),
        )
        content = "\n\n".join(doc for _, doc in pairs)
        meta = pairs[0][0]
        note: dict = {"file_path": path, "content": content}
        if meta.get("source"):
            note["source"] = meta["source"]
        if meta.get("paperless_doc_id"):
            note["paperless_doc_id"] = meta["paperless_doc_id"]
        return note


def query_paperless_doc_ids(
    tags: Optional[list[str]] = None,
    correspondent: Optional[str] = None,
    created_year: Optional[int] = None,
) -> Optional[list[str]]:
    """Query the Paperless API with structured filters and return matching doc IDs.

    Returns None if no filters are given (= no pre-filtering).
    Returns an empty list if filters are given but nothing matches.
    """
    from .config import PAPERLESS_URL, PAPERLESS_TOKEN

    if not PAPERLESS_URL or not PAPERLESS_TOKEN:
        return None

    has_filter = bool(tags or correspondent or created_year)
    if not has_filter:
        return None

    import requests

    params: dict = {"fields": "id", "page_size": 500}
    if tags:
        # tags__name__icontains accepts a single string; for multiple tags
        # we issue one query per tag and intersect the results.
        if len(tags) == 1:
            params["tags__name__icontains"] = tags[0]
        else:
            # Multiple tags → intersect doc IDs from individual queries
            id_sets: list[set[str]] = []
            for tag in tags:
                tag_params = dict(params)
                tag_params["tags__name__icontains"] = tag
                if correspondent:
                    tag_params["correspondent__name__icontains"] = correspondent
                if created_year:
                    tag_params["created__year"] = created_year
                try:
                    resp = requests.get(
                        f"{PAPERLESS_URL}/api/documents/",
                        params=tag_params,
                        headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
                        timeout=10,
                    )
                    if not resp.ok:
                        logger.warning("Paperless filter query failed: %s", resp.status_code)
                        return None
                    data = resp.json()
                    id_sets.append({str(doc["id"]) for doc in data.get("results", [])})
                except Exception:
                    logger.exception("Paperless filter query error")
                    return None
            result_ids = id_sets[0]
            for s in id_sets[1:]:
                result_ids &= s
            return sorted(result_ids)
    if correspondent:
        params["correspondent__name__icontains"] = correspondent
    if created_year:
        params["created__year"] = created_year

    try:
        resp = requests.get(
            f"{PAPERLESS_URL}/api/documents/",
            params=params,
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
            timeout=10,
        )
        if not resp.ok:
            logger.warning("Paperless filter query failed: %s", resp.status_code)
            return None
        data = resp.json()
        doc_ids = [str(doc["id"]) for doc in data.get("results", [])]
        return doc_ids
    except Exception:
        logger.exception("Paperless filter query error")
        return None

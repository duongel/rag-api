"""Semantic and keyword search across the indexed Obsidian vault."""

import logging
import re
from pathlib import Path
from typing import Optional

from .config import VAULT_PATH, DATA_SOURCES, PAPERLESS_URL, PAPERLESS_TOKEN
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
        paperless_tags: Optional[list[str]] = None,
        paperless_correspondent: Optional[str] = None,
        paperless_created_year: Optional[int] = None,
        paperless_document_type: Optional[str] = None,
        sort_by_date: bool = False,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Embed *query*, return the most similar chunks, and optionally
        append linked notes up to 2 degrees of separation.

        Paperless filter parameters build a ChromaDB ``where`` clause so
        only matching documents are considered.

        When *sort_by_date* is True, results above ``min_score`` are
        re-sorted by creation date (newest first).  This is useful for
        queries like "letzte Rechnung" where recency matters more than
        marginal score differences.
        """
        query_embedding = embed_query(query)

        where = _build_chromadb_filters(
            paperless_tags, paperless_correspondent, paperless_created_year,
            paperless_document_type,
        )

        # Fetch more than top_k so that deduplication (which collapses
        # multiple chunks from the same document/section) doesn't
        # under-fill the result set.  Both paths use the same adaptive
        # widening loop: start with a generous initial window, dedup,
        # and double the fetch size when unique results are still below
        # top_k.  Date-sorting gets a wider initial window because we
        # need to capture truly newest documents regardless of score.
        corpus_size = self.collection.count() or 1
        fetch_k = max(top_k * 20, 200) if sort_by_date else top_k * 3

        output: list[dict] = []
        _MAX_WIDEN_ITERS = 8  # safety cap: at most 256× initial window
        for _ in range(_MAX_WIDEN_ITERS):
            actual_k = min(fetch_k, corpus_size)
            query_kwargs: dict = {
                "query_embeddings": [query_embedding],
                "n_results": actual_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_kwargs["where"] = where

            results = self.collection.query(**query_kwargs)
            raw = self._parse_query_results(results)
            output = self._dedup_results(raw)

            if len(output) >= top_k or actual_k >= corpus_size:
                break
            # When a filter is active, ChromaDB may return fewer rows
            # than requested because matching candidates are exhausted.
            if len(raw) < actual_k:
                break
            # Double the window for the next attempt
            fetch_k = min(fetch_k * 2, corpus_size)

        if expand_links and not where:
            # For score-ranked search, only seed graph expansion with the
            # best top_k semantic hits so low-relevance tails do not
            # promote unrelated linked notes.
            #
            # For date-sorted search, keep the full widened semantic
            # candidate pool so newer documents outside the score top_k
            # are still eligible after date reordering.
            seed_k = len(output) if sort_by_date else top_k
            seeds = sorted(output, key=lambda r: r["score"], reverse=True)[:seed_k]
            output = self._expand_with_links(seeds, query_embedding, seed_k)

        if sort_by_date:
            if min_score > 0:
                output = [r for r in output if r["score"] >= min_score]
            output.sort(
                key=lambda r: r.get("created", ""),
                reverse=True,
            )

        return output[:top_k]

    @staticmethod
    def _parse_query_results(results: dict) -> list[dict]:
        """Convert raw ChromaDB query output into a flat result list."""
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
            if meta.get("created"):
                entry["created"] = meta["created"]
            output.append(entry)
        return output

    @staticmethod
    def _dedup_results(results: list[dict]) -> list[dict]:
        """Keep only the best-scoring entry per source/file/section tuple."""
        deduped: dict[str, dict] = {}
        for result in results:
            key = Searcher._result_key(result)
            current = deduped.get(key)
            if current is None or result["score"] > current["score"]:
                deduped[key] = result
        return list(deduped.values())

    @staticmethod
    def _result_key(result: dict, *, collapse_paperless_sections: bool = False) -> str:
        """Build a stable dedup key for search results.

        When ``collapse_paperless_sections`` is enabled, Paperless hits are
        deduplicated on document level (source + file path) so filename hits
        and chunk hits cannot appear as duplicates for the same PDF.
        """
        source = result.get("source", "obsidian")
        file_path = result["file_path"]
        if collapse_paperless_sections and source == "paperless":
            return f"{source}::{file_path}"
        return f"{source}::{file_path}#{result.get('section', '')}"

    @staticmethod
    def _make_keyword_entry(meta: dict, doc: str, score: float) -> dict:
        """Build a keyword-search result dict from chunk metadata."""
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
        if meta.get("created"):
            entry["created"] = meta["created"]
        return entry

    # ------------------------------------------------------------------
    # Hybrid search (semantic + keyword)
    # ------------------------------------------------------------------

    # German stop words filtered out when building keyword queries from
    # natural-language input in hybrid search.
    _STOP_WORDS: set = {
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer",
        "einem", "einen", "und", "oder", "aber", "als", "auch", "auf",
        "aus", "bei", "bis", "da", "dass", "denn", "doch", "du", "er",
        "es", "für", "hat", "ich", "ihr", "im", "in", "ist", "ja",
        "kann", "man", "mit", "nach", "nicht", "noch", "nun", "nur",
        "ob", "schon", "sich", "sie", "sind", "so", "über", "um",
        "von", "vor", "was", "wenn", "wer", "wie", "wir", "wird",
        "zu", "zum", "zur", "alle", "wann", "war", "were", "vom",
        "suche", "summiere", "zeige", "finde", "liste",
    }

    # German query-term expansion for hybrid search.  When a content
    # word appears as a key, the synonyms are *added* to the keyword
    # coverage check so that semantically related documents get a boost.
    _QUERY_EXPANSIONS: dict = {
        "kosten": ["rechnung", "betrag", "beitrag", "zahlung", "gebühr", "preis"],
        "rechnung": ["betrag", "kosten", "zahlung", "invoice"],
        "kaufvertrag": ["kauf", "vertrag", "urkunde", "notar"],
        "vertrag": ["kaufvertrag", "urkunde", "vereinbarung"],
        "miete": ["mietvertrag", "kaltmiete", "warmmiete", "nebenkosten"],
        "gehalt": ["lohn", "vergütung", "abrechnung", "brutto", "netto"],
        "steuer": ["steuerbescheid", "finanzamt", "einkommensteuer"],
        "versicherung": ["police", "beitrag", "versicherungsschein"],
    }

    def hybrid_search(
        self, query: str, top_k: int = 5,
        expand_links: bool = True,
        paperless_tags: Optional[list[str]] = None,
        paperless_correspondent: Optional[str] = None,
        paperless_created_year: Optional[int] = None,
        paperless_document_type: Optional[str] = None,
        sort_by_date: bool = False,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Run semantic **and** keyword search, merge and deduplicate.

        The keyword search uses a cleaned version of the query with stop
        words removed so that multi-word AND matching works on the
        content words (e.g. "summiere alle kosten für den vw golf"
        becomes keyword query "kosten vw golf").

        After merging, a **keyword/synonym re-rank** adds a small boost
        for exact term coverage and additional synonym coverage. Exact
        matches are never penalized for not containing all synonyms.
        """
        # When sorting by date we need wider candidate pools so that
        # truly newest documents are captured even when they aren't
        # among the top-k most relevant results.
        candidate_k = top_k * 10 if sort_by_date else top_k * 3

        sem_results = self.semantic_search(
            query,
            top_k=candidate_k,
            expand_links=expand_links,
            paperless_tags=paperless_tags,
            paperless_correspondent=paperless_correspondent,
            paperless_created_year=paperless_created_year,
            paperless_document_type=paperless_document_type,
            sort_by_date=sort_by_date,
            # Apply min_score after hybrid merge/rerank so documents are
            # not dropped before cross-method and keyword/synonym boosts.
            min_score=0.0,
        )

        # Build a keyword query from content words only
        content_words = [
            w for w in query.lower().split()
            if w not in self._STOP_WORDS and len(w) > 1
        ]
        kw_query = " ".join(content_words) if content_words else query

        kw_results = self.keyword_search(
            kw_query, top_k=candidate_k if sort_by_date else top_k,
            paperless_tags=paperless_tags,
            paperless_correspondent=paperless_correspondent,
            paperless_created_year=paperless_created_year,
            paperless_document_type=paperless_document_type,
        )

        # Merge result sets using stable dedup keys.
        # Paperless items are deduped by document path so filename and chunk
        # matches for the same PDF do not appear twice.
        seen: dict[str, dict] = {}
        sem_keys: set[str] = set()
        kw_keys: set[str] = set()

        for r in sem_results:
            key = self._result_key(r, collapse_paperless_sections=True)
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r
            sem_keys.add(key)

        for r in kw_results:
            key = self._result_key(r, collapse_paperless_sections=True)
            kw_keys.add(key)
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r

        # Cross-method bonus: docs found by BOTH methods are more relevant
        _CROSS_BONUS = 0.05
        for key in sem_keys & kw_keys:
            seen[key] = dict(seen[key])
            seen[key]["score"] = round(seen[key]["score"] + _CROSS_BONUS, 4)

        # ── Keyword/synonym re-rank ──
        # Exact content words should never be penalized because a synonym is
        # missing. Instead, exact and synonym hits provide additive boosts.
        exact_terms = set(content_words)
        synonym_terms: set[str] = set()
        for w in content_words:
            synonym_terms.update(self._QUERY_EXPANSIONS.get(w, []))
        synonym_terms -= exact_terms

        if exact_terms or synonym_terms:
            for key, r in seen.items():
                doc_lower = r.get("content", "").lower()
                r = dict(r)

                exact_cov = 0.0
                if exact_terms:
                    exact_cov = sum(1 for t in exact_terms if t in doc_lower) / len(exact_terms)

                synonym_cov = 0.0
                if synonym_terms:
                    synonym_cov = sum(1 for t in synonym_terms if t in doc_lower) / len(synonym_terms)

                bonus = (0.05 * exact_cov) + (0.10 * synonym_cov)
                r["score"] = round(r["score"] + bonus, 4)
                seen[key] = r

        merged = list(seen.values())

        if min_score > 0:
            merged = [r for r in merged if r["score"] >= min_score]

        if sort_by_date:
            merged.sort(key=lambda r: r.get("created", ""), reverse=True)
        else:
            merged.sort(key=lambda r: r["score"], reverse=True)

        return merged[:top_k]

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
    ) -> Optional[dict]:
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
                if meta.get("created"):
                    entry["created"] = meta["created"]
                return entry
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Keyword / exact-match search
    # ------------------------------------------------------------------

    def keyword_search(
        self, query: str, top_k: int = 10,
        paperless_tags: Optional[list[str]] = None,
        paperless_correspondent: Optional[str] = None,
        paperless_created_year: Optional[int] = None,
        paperless_document_type: Optional[str] = None,
    ) -> list[dict]:
        """Search filenames and document content for *query* (case-insensitive).

        Multi-word queries use AND logic: every word must appear in the
        document.  Single-word queries match as a substring as before.

        Scoring is based on match location, word-boundary matches, and
        frequency so that results containing the query more often or as a
        whole word rank higher.

        Paperless filter parameters are mapped to ChromaDB ``where``
        conditions so only matching chunks participate.
        """
        where = _build_chromadb_filters(
            paperless_tags, paperless_correspondent, paperless_created_year,
            paperless_document_type,
        )
        has_filter = where is not None

        allowed_file_paths: Optional[set[str]] = None
        if has_filter:
            try:
                filter_docs = self.collection.get(where=where, include=["metadatas"])
                allowed_file_paths = {
                    m.get("file_path", "")
                    for m in (filter_docs.get("metadatas") or [])
                    if m.get("file_path")
                }
            except Exception:
                allowed_file_paths = set()
            if not allowed_file_paths:
                return []

        query_lower = query.lower()
        terms = query_lower.split()
        multi_word = len(terms) > 1

        word_pattern = re.compile(r"\b" + re.escape(query_lower) + r"\b", re.IGNORECASE)
        term_patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
            for t in terms
        ] if multi_word else [word_pattern]

        results: list[dict] = []
        seen: set[str] = set()

        # 1) Filename matches
        for doc_key, source in self.indexer._file_sources.items():
            fp = self.indexer._file_path_from_key(doc_key)
            fp_lower = fp.lower()
            if multi_word:
                if not all(t in fp_lower for t in terms):
                    continue
            else:
                if query_lower not in fp_lower:
                    continue
            if has_filter:
                if source != "paperless":
                    continue
                if allowed_file_paths is not None and fp not in allowed_file_paths:
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
                seen.add(self._result_key({"source": source, "file_path": fp}, collapse_paperless_sections=True))
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
                seen.add(self._result_key({"source": source, "file_path": fp}, collapse_paperless_sections=True))

        # 2) Content matches — always case-insensitive via full scan
        try:
            get_kwargs: dict = {"include": ["documents", "metadatas"]}
            if where is not None:
                get_kwargs["where"] = where
            all_docs = self.collection.get(**get_kwargs)

            # Track index into results list per dedup key so we can
            # replace a weaker chunk with a higher-scoring one, or enrich
            # existing filename hits with metadata (e.g., paperless_doc_id)
            # from matching content chunks.
            key_to_idx: dict[str, int] = {
                self._result_key(r, collapse_paperless_sections=True): idx
                for idx, r in enumerate(results)
            }

            if multi_word:
                # Evaluate AND across all chunks of the same document so
                # that terms split across different chunks still match.
                from collections import defaultdict
                file_chunks: dict[str, list[tuple[str, dict]]] = defaultdict(list)
                for i, doc in enumerate(all_docs["documents"] or []):
                    meta = all_docs["metadatas"][i]
                    file_key = f"{meta.get('source', 'obsidian')}::{meta['file_path']}"
                    file_chunks[file_key].append((doc, meta))

                for file_key, chunks in file_chunks.items():
                    combined_lower = " ".join(doc.lower() for doc, _ in chunks)
                    if not all(t in combined_lower for t in terms):
                        continue
                    for doc, meta in chunks:
                        doc_lower = doc.lower()
                        if not any(t in doc_lower for t in terms):
                            continue
                        key = self._result_key(meta, collapse_paperless_sections=True)
                        score = self._keyword_score_multi(doc, terms, term_patterns)
                        if key in seen:
                            prev_idx = key_to_idx.get(key)
                            if prev_idx is not None:
                                if score > results[prev_idx]["score"]:
                                    results[prev_idx] = self._make_keyword_entry(meta, doc, score)
                                else:
                                    enriched = self._make_keyword_entry(meta, doc, score)
                                    if not results[prev_idx].get("paperless_doc_id") and enriched.get("paperless_doc_id"):
                                        results[prev_idx]["paperless_doc_id"] = enriched["paperless_doc_id"]
                                    if not results[prev_idx].get("source_url") and enriched.get("source_url"):
                                        results[prev_idx]["source_url"] = enriched["source_url"]
                            continue
                        entry = self._make_keyword_entry(meta, doc, score)
                        key_to_idx[key] = len(results)
                        results.append(entry)
                        seen.add(key)
            else:
                for i, doc in enumerate(all_docs["documents"] or []):
                    doc_lower = doc.lower()
                    if query_lower not in doc_lower:
                        continue
                    meta = all_docs["metadatas"][i]
                    key = self._result_key(meta, collapse_paperless_sections=True)
                    score = self._keyword_score(doc, query_lower, word_pattern)
                    if key in seen:
                        prev_idx = key_to_idx.get(key)
                        if prev_idx is not None:
                            if score > results[prev_idx]["score"]:
                                results[prev_idx] = self._make_keyword_entry(meta, doc, score)
                            else:
                                enriched = self._make_keyword_entry(meta, doc, score)
                                if not results[prev_idx].get("paperless_doc_id") and enriched.get("paperless_doc_id"):
                                    results[prev_idx]["paperless_doc_id"] = enriched["paperless_doc_id"]
                                if not results[prev_idx].get("source_url") and enriched.get("source_url"):
                                    results[prev_idx]["source_url"] = enriched["source_url"]
                        continue
                    entry = self._make_keyword_entry(meta, doc, score)
                    key_to_idx[key] = len(results)
                    results.append(entry)
                    seen.add(key)

            # Backfill created dates for filename matches from content metadata
            created_by_key: dict[str, str] = {}
            for meta in (all_docs.get("metadatas") or []):
                fp = meta.get("file_path", "")
                source = meta.get("source", "obsidian")
                created = meta.get("created", "")
                key = f"{source}::{fp}"
                if fp and created and key not in created_by_key:
                    created_by_key[key] = created
            for r in results:
                if not r.get("created"):
                    key = f"{r.get('source', 'obsidian')}::{r['file_path']}"
                    if key in created_by_key:
                        r["created"] = created_by_key[key]
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

    @staticmethod
    def _keyword_score_multi(
        doc: str, terms: list[str], term_patterns: list[re.Pattern[str]],
    ) -> float:
        """Score a document against multiple AND-ed keyword terms.

        Base score is 0.70.  Per-term bonuses (averaged):
        - frequency:  +0.03 per occurrence (max +0.15)
        - whole-word: +0.05 if at least one word-boundary match
        - proximity:  +0.05 if any two terms appear within 200 chars of each other
        """
        doc_lower = doc.lower()
        total_freq = 0.0
        total_word = 0.0
        all_positions: list[int] = []
        for term, pattern in zip(terms, term_patterns):
            count = doc_lower.count(term)
            total_freq += min(count * 0.03, 0.15)
            if pattern.search(doc):
                total_word += 0.05
            # Collect ALL occurrences so proximity check considers
            # close later occurrences, not just distant first ones.
            start = 0
            while True:
                pos = doc_lower.find(term, start)
                if pos < 0:
                    break
                all_positions.append(pos)
                start = pos + 1
        n = len(terms)
        avg_freq = total_freq / n
        avg_word = total_word / n
        # Proximity bonus: any two matched terms within 200 chars
        proximity_bonus = 0.0
        if len(all_positions) >= 2:
            all_positions.sort()
            for j in range(len(all_positions) - 1):
                if all_positions[j + 1] - all_positions[j] < 200:
                    proximity_bonus = 0.05
                    break
        return round(0.70 + avg_freq + avg_word + proximity_bonus, 4)

    # ------------------------------------------------------------------
    # Single note retrieval
    # ------------------------------------------------------------------

    def get_note(self, path: str) -> Optional[dict]:
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

    def _get_note_from_index(self, path: str) -> Optional[dict]:
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


def _build_chromadb_filters(
    tags: Optional[list[str]] = None,
    correspondent: Optional[str] = None,
    created_year: Optional[int] = None,
    document_type: Optional[str] = None,
) -> Optional[dict]:
    """Build a ChromaDB ``where`` filter by querying the Paperless API first.

    When Paperless credentials are configured and at least one filter is set,
    this function queries the Paperless REST API to obtain the exact set of
    matching document IDs.  The IDs are turned into a ChromaDB ``$or``
    filter on ``paperless_doc_id``.

    This is more accurate than replicating Paperless metadata in ChromaDB
    because Paperless handles tags, document types, correspondents, and
    date ranges authoritatively — including manually-assigned tags that
    don't appear anywhere in the document text.

    Falls back to basic ``{"source": "paperless"}`` if no filters are
    provided, and to ``None`` if Paperless is not configured.
    """
    has_filter = any([tags, correspondent, created_year, document_type])
    if not has_filter:
        return None

    # Try Paperless API pre-filter (authoritative)
    if PAPERLESS_URL and PAPERLESS_TOKEN:
        # Cap passed into the API helper so it can short-circuit
        # pagination instead of fetching all matching IDs first.
        _MAX_OR_IDS = 200
        doc_ids = _query_paperless_api(
            tags=tags,
            correspondent=correspondent,
            created_year=created_year,
            document_type=document_type,
            max_ids=_MAX_OR_IDS,
        )
        if doc_ids is not None:
            if not doc_ids:
                # Paperless returned 0 matches → short-circuit
                return {"paperless_doc_id": "__NO_MATCH__"}
            # Fall back to legacy metadata filters when the set is
            # too large for a single $or clause.
            if len(doc_ids) > _MAX_OR_IDS:
                logger.info(
                    "Paperless pre-filter matched %d docs (> %d); "
                    "falling back to metadata filters",
                    len(doc_ids), _MAX_OR_IDS,
                )
            elif len(doc_ids) == 1:
                return {"paperless_doc_id": doc_ids[0]}
            else:
                return {"$or": [{"paperless_doc_id": did} for did in doc_ids]}

    # Fallback: basic ChromaDB metadata filter (legacy)
    conditions: list[dict] = [{"source": "paperless"}]
    if created_year is not None:
        conditions.append({"created_year": created_year})
    if correspondent:
        conditions.append({"correspondent_name_lc": correspondent.lower()})
    if tags:
        for tag in tags:
            conditions.append({f"ptag_{tag.lower()}": 1})
    if document_type:
        conditions.append({"document_type_name_lc": document_type.lower()})
    return {"$and": conditions} if len(conditions) > 1 else conditions[0]


# ---------------------------------------------------------------------------
# Paperless API pre-filter
# ---------------------------------------------------------------------------

# Cache: tag name (lowercase) → tag ID
_TAG_NAME_TO_ID: dict[str, int] = {}
# Cache: document type name (lowercase) → type ID
_DOCTYPE_NAME_TO_ID: dict[str, int] = {}
# Cache: correspondent name (lowercase) → correspondent ID
_CORR_NAME_TO_ID: dict[str, int] = {}
# Track whether each cache was fully populated (all pages fetched)
_LOOKUP_COMPLETE: dict[str, bool] = {"tags": False, "doctypes": False, "corrs": False}
# Timestamp of last successful full refresh (monotonic seconds)
_LOOKUP_LAST_REFRESH: float = 0.0
# Auto-refresh interval in seconds (covers renames in Paperless)
_LOOKUP_TTL: float = 300.0


def _ensure_paperless_lookups(
    force_refresh: bool = False,
    *,
    need_tags: bool = False,
    need_doctypes: bool = False,
    need_corrs: bool = False,
) -> None:
    """Lazily fetch and cache required Paperless lookups only.

    Avoids fetching unrelated lookup tables (which can add tens of seconds
    of latency during API outages) when only one filter type is needed.
    """
    import requests
    import time

    global _LOOKUP_LAST_REFRESH

    headers = {"Authorization": f"Token {PAPERLESS_TOKEN}"}

    # Auto-refresh when the cache is older than _LOOKUP_TTL so that
    # renamed tags/correspondents/document types don't stay stale.
    if not force_refresh and _LOOKUP_LAST_REFRESH > 0:
        if (time.monotonic() - _LOOKUP_LAST_REFRESH) >= _LOOKUP_TTL:
            force_refresh = True

    if force_refresh:
        if need_tags:
            _TAG_NAME_TO_ID.clear()
            _LOOKUP_COMPLETE["tags"] = False
        if need_doctypes:
            _DOCTYPE_NAME_TO_ID.clear()
            _LOOKUP_COMPLETE["doctypes"] = False
        if need_corrs:
            _CORR_NAME_TO_ID.clear()
            _LOOKUP_COMPLETE["corrs"] = False

    if need_tags and not _LOOKUP_COMPLETE["tags"] and not _TAG_NAME_TO_ID:
        try:
            url: Optional[str] = f"{PAPERLESS_URL}/api/tags/"
            params: Optional[dict] = {"page_size": 500}
            complete = True
            while url:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if not resp.ok:
                    complete = False
                    break
                data = resp.json()
                for t in data.get("results", []):
                    name = str(t.get("name", "")).strip()
                    if name:
                        _TAG_NAME_TO_ID[name.lower()] = t["id"]
                url = data.get("next")
                params = None
            _LOOKUP_COMPLETE["tags"] = complete
        except Exception:
            _LOOKUP_COMPLETE["tags"] = False

    if need_doctypes and not _LOOKUP_COMPLETE["doctypes"] and not _DOCTYPE_NAME_TO_ID:
        try:
            url = f"{PAPERLESS_URL}/api/document_types/"
            params = {"page_size": 500}
            complete = True
            while url:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if not resp.ok:
                    complete = False
                    break
                data = resp.json()
                for dt in data.get("results", []):
                    name = str(dt.get("name", "")).strip()
                    if name:
                        _DOCTYPE_NAME_TO_ID[name.lower()] = dt["id"]
                url = data.get("next")
                params = None
            _LOOKUP_COMPLETE["doctypes"] = complete
        except Exception:
            _LOOKUP_COMPLETE["doctypes"] = False

    if need_corrs and not _LOOKUP_COMPLETE["corrs"] and not _CORR_NAME_TO_ID:
        try:
            url = f"{PAPERLESS_URL}/api/correspondents/"
            params = {"page_size": 500}
            complete = True
            while url:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if not resp.ok:
                    complete = False
                    break
                data = resp.json()
                for c in data.get("results", []):
                    name = str(c.get("name", "")).strip()
                    if name:
                        _CORR_NAME_TO_ID[name.lower()] = c["id"]
                url = data.get("next")
                params = None
            _LOOKUP_COMPLETE["corrs"] = complete
        except Exception:
            _LOOKUP_COMPLETE["corrs"] = False

    # Record refresh timestamp when all three caches completed
    if all(_LOOKUP_COMPLETE.values()):
        _LOOKUP_LAST_REFRESH = time.monotonic()


def _query_paperless_api(
    tags: Optional[list[str]] = None,
    correspondent: Optional[str] = None,
    created_year: Optional[int] = None,
    document_type: Optional[str] = None,
    max_ids: int = 0,
) -> Optional[list[str]]:
    """Query the Paperless REST API and return matching document IDs.

    Returns None on API failure (caller should fall back to ChromaDB
    metadata).  Returns an empty list when the query matched zero
    documents.  When *max_ids* > 0, pagination is aborted early once
    the threshold is exceeded (the returned list will contain more than
    *max_ids* entries so the caller knows the cap was hit).
    """
    import requests

    _ensure_paperless_lookups(
        need_tags=bool(tags),
        need_doctypes=bool(document_type),
        need_corrs=bool(correspondent),
    )

    headers = {"Authorization": f"Token {PAPERLESS_TOKEN}"}
    params: dict = {"page_size": 500, "fields": "id"}

    # Resolve tag names → IDs
    if tags:
        tag_ids = []
        for tag_name in tags:
            tid = _TAG_NAME_TO_ID.get(tag_name.lower())
            if tid is None:
                _ensure_paperless_lookups(force_refresh=True, need_tags=True)
                tid = _TAG_NAME_TO_ID.get(tag_name.lower())
                if tid is None:
                    if not _LOOKUP_COMPLETE["tags"]:
                        logger.warning("Paperless tag lookup incomplete; falling back to metadata filters")
                        return None
                    logger.warning("Paperless tag '%s' not found", tag_name)
                    return []  # unknown tag → 0 matches
            tag_ids.append(str(tid))
        params["tags__id__all"] = ",".join(tag_ids)

    # Resolve document type name → ID
    if document_type:
        dtid = _DOCTYPE_NAME_TO_ID.get(document_type.lower())
        if dtid is None:
            _ensure_paperless_lookups(force_refresh=True, need_doctypes=True)
            dtid = _DOCTYPE_NAME_TO_ID.get(document_type.lower())
            if dtid is None:
                if not _LOOKUP_COMPLETE["doctypes"]:
                    logger.warning("Paperless doctype lookup incomplete; falling back to metadata filters")
                    return None
                logger.warning("Paperless document type '%s' not found", document_type)
                return []
        params["document_type__id__in"] = str(dtid)

    # Resolve correspondent name → ID
    if correspondent:
        cid = _CORR_NAME_TO_ID.get(correspondent.lower())
        if cid is None:
            _ensure_paperless_lookups(force_refresh=True, need_corrs=True)
            cid = _CORR_NAME_TO_ID.get(correspondent.lower())
            if cid is None:
                if not _LOOKUP_COMPLETE["corrs"]:
                    logger.warning("Paperless correspondent lookup incomplete; falling back to metadata filters")
                    return None
                logger.warning("Paperless correspondent '%s' not found", correspondent)
                return []
        params["correspondent__id"] = str(cid)

    # Date range filter
    if created_year:
        params["query"] = f"created:[{created_year}-01-01 TO {created_year}-12-31]"

    try:
        all_ids: list[str] = []
        url: Optional[str] = f"{PAPERLESS_URL}/api/documents/"
        page_params: Optional[dict] = params
        while url:
            resp = requests.get(url, params=page_params, headers=headers, timeout=15)
            if not resp.ok:
                logger.error("Paperless API returned %d", resp.status_code)
                return None
            data = resp.json()
            for doc in data.get("results", []):
                all_ids.append(str(doc["id"]))
            # Short-circuit when we already exceed the caller's cap —
            # no need to paginate through thousands of IDs.
            if max_ids and len(all_ids) > max_ids:
                logger.info(
                    "Paperless pre-filter exceeded %d IDs, stopping early",
                    max_ids,
                )
                return all_ids
            url = data.get("next")
            page_params = None  # next URL already contains params
        logger.info(
            "Paperless pre-filter: %d docs (tags=%s type=%s year=%s)",
            len(all_ids), tags, document_type, created_year,
        )
        return all_ids
    except Exception as e:
        logger.error("Paperless API query failed: %s", e)
        return None

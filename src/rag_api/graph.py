"""In-memory wikilink graph for the Obsidian vault.

Stores directed edges  file_path → {linked file_paths}  and provides
BFS-based neighbourhood queries up to a configurable degree.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LinkGraph:
    """Lightweight in-memory graph rebuilt during indexing.

    Resolution strategy (mirrors Obsidian):
      1. Exact path match:  [[Projects/Home/Heating]]  → ``Projects/Home/Heating.md``
      2. Stem-only match:   [[Heating]]                → shortest path whose stem matches
    """

    def __init__(self) -> None:
        # file_path → set of resolved linked file_paths  (wikilinks, outgoing)
        self._edges: dict[str, set[str]] = {}
        # target → set of files that link TO it  (backlinks)
        self._reverse_edges: dict[str, set[str]] = {}
        # lowercase stem → file_path  (shortest-path wins on collision)
        self._name_map: dict[str, str] = {}
        # all known file paths (for path-suffix resolution)
        self._all_files: set[str] = set()
        # tag → set of file_paths  (for tag-based connections)
        self._tag_to_files: dict[str, set[str]] = {}
        # file_path → set of tags  (for cleanup on remove)
        self._file_tags: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, file_path: str) -> None:
        """Register *file_path* so wikilinks can resolve to it."""
        self._all_files.add(file_path)
        stem = Path(file_path).stem.lower()
        # Keep the shortest path for ambiguous stems (Obsidian default)
        if stem not in self._name_map or len(file_path) < len(self._name_map[stem]):
            self._name_map[stem] = file_path

    # ------------------------------------------------------------------
    # Graph mutations
    # ------------------------------------------------------------------

    def update(self, file_path: str, raw_link_texts: list[str]) -> None:
        """Resolve *raw_link_texts* and store outgoing edges for *file_path*."""
        # Remove stale reverse-edge entries
        for old_target in self._edges.get(file_path, set()):
            self._reverse_edges.get(old_target, set()).discard(file_path)

        resolved: set[str] = set()
        for link in raw_link_texts:
            target = self.resolve(link)
            if target and target != file_path:
                resolved.add(target)

        self._edges[file_path] = resolved

        # Build reverse index
        for target in resolved:
            self._reverse_edges.setdefault(target, set()).add(file_path)

        logger.debug("graph.update %s → %d links", file_path, len(resolved))

    def remove(self, file_path: str) -> None:
        """Remove *file_path* and its outgoing edges from the graph."""
        # Clean up reverse edges for targets we used to point to
        for target in self._edges.pop(file_path, set()):
            self._reverse_edges.get(target, set()).discard(file_path)
        # Clean up reverse edges where others pointed to us
        self._reverse_edges.pop(file_path, None)
        # Remove stale outgoing references from all remaining nodes
        for edges in self._edges.values():
            edges.discard(file_path)

        self._all_files.discard(file_path)
        stem = Path(file_path).stem.lower()
        if self._name_map.get(stem) == file_path:
            alts = [f for f in self._all_files if Path(f).stem.lower() == stem]
            if alts:
                self._name_map[stem] = min(alts, key=len)
            else:
                self._name_map.pop(stem, None)
        # Clean up tag associations
        for tag in self._file_tags.pop(file_path, set()):
            self._tag_to_files.get(tag, set()).discard(file_path)

    # ------------------------------------------------------------------
    # Tag-based connections
    # ------------------------------------------------------------------

    def update_tags(self, file_path: str, tags: list[str]) -> None:
        """Store the tag set for *file_path* and update the tag→files index.

        Tag names should already be normalised (lowercase, no leading ``#``).
        """
        # Remove stale associations
        for tag in self._file_tags.pop(file_path, set()):
            self._tag_to_files.get(tag, set()).discard(file_path)

        normalised = {t.strip().lower().lstrip("#") for t in tags if t}
        self._file_tags[file_path] = normalised
        for tag in normalised:
            self._tag_to_files.setdefault(tag, set()).add(file_path)
        logger.debug("graph.update_tags %s → %s", file_path, normalised)

    def tag_neighbors(self, file_path: str) -> set[str]:
        """Return all files that share at least one tag with *file_path*."""
        result: set[str] = set()
        for tag in self._file_tags.get(file_path, set()):
            result |= self._tag_to_files.get(tag, set())
        result.discard(file_path)
        return result

    def backlink_neighbors(self, file_path: str) -> set[str]:
        """Return all files that contain a wikilink pointing TO *file_path*."""
        return self._reverse_edges.get(file_path, set()) - {file_path}

    # ------------------------------------------------------------------
    # Resolution & traversal
    # ------------------------------------------------------------------

    def resolve(self, link_text: str) -> Optional[str]:
        """Resolve an Obsidian wikilink target to a relative file path."""
        link_text = link_text.strip()
        if not link_text:
            return None

        # Strip .md suffix for uniform comparison
        target = link_text[:-3] if link_text.lower().endswith(".md") else link_text
        suffix = target.lower() + ".md"

        # 1) Exact or trailing-path match: [[folder/Note]] → «folder/Note.md»
        for fp in self._all_files:
            if fp.lower() == suffix or fp.lower().endswith("/" + suffix):
                return fp

        # 2) Stem-only fallback: [[Note]] → shortest «*.../Note.md»
        return self._name_map.get(Path(target).stem.lower())

    def neighbors(self, file_path: str, max_degree: int = 2) -> dict[str, int]:
        """BFS from *file_path* up to *max_degree* hops.

        Returns ``{neighbor_file_path: degree}`` for every reachable node,
        excluding the origin.  Cycles are handled via a visited set.
        """
        visited: dict[str, int] = {}
        frontier: set[str] = {file_path}

        for degree in range(1, max_degree + 1):
            next_frontier: set[str] = set()
            for fp in frontier:
                for nb in self._edges.get(fp, set()):
                    if nb not in visited and nb != file_path:
                        visited[nb] = degree
                        next_frontier.add(nb)
            frontier = next_frontier
            if not frontier:
                break

        return visited

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Number of resolved outgoing edges in the graph."""
        return sum(len(edges) for edges in self._edges.values())

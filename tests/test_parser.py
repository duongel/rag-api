"""Tests for the RecursiveCharacterTextSplitter with Markdown/Callout awareness.

These tests use the fictional ``tests/fixtures/Erfolgsjournal.md`` which mirrors
the structure of a real Obsidian Erfolgsjournal: Callout blocks
(``> [!j-header]``, ``> [!j-gratitude]``, …) separated by ``---`` thematic breaks,
**without** any Markdown headers (``#``/``##``/``###``).

The tests encode the *desired* behaviour: each day-entry should become its own
chunk, split at ``---`` boundaries, with the date extracted as section name.
"""

import re
from pathlib import Path

import pytest

from rag_api.config import MAX_CHUNK_SIZE, CHUNK_DISCARD_LENGTH
from rag_api.parser import (
    Chunk,
    parse_markdown,
    _split_by_headers,
    _split_by_thematic_breaks,
    _recursive_split,
    _merge_splits,
    _hard_split,
    _make_chunk,
    resolve_wikilinks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)"
    r",\s+\d{2}\.\d{2}\.\d{4}"
)

FIXTURE_FILE = "Erfolgsjournal.md"


def _count_day_entries(fixture_path: Path) -> int:
    """Count the number of ``> [!j-header]`` lines in the fixture file."""
    text = (fixture_path / FIXTURE_FILE).read_text(encoding="utf-8")
    return text.count("> [!j-header]")


# ---------------------------------------------------------------------------
# Chunking correctness for Callout-based journals
# ---------------------------------------------------------------------------


class TestErfolgsjournalChunking:
    """Verify that a Callout-based Erfolgsjournal is chunked correctly."""

    @pytest.fixture(autouse=True)
    def _parse(self, fixtures_dir: Path) -> None:
        self.chunks = parse_markdown(FIXTURE_FILE, str(fixtures_dir))
        self.fixture_path = fixtures_dir
        self.day_count = _count_day_entries(fixtures_dir)

    # -- size constraints --------------------------------------------------

    def test_all_chunks_within_max_size(self):
        """Every chunk must respect ``MAX_CHUNK_SIZE``."""
        for i, chunk in enumerate(self.chunks):
            assert len(chunk.content) <= MAX_CHUNK_SIZE, (
                f"Chunk {i} exceeds MAX_CHUNK_SIZE ({len(chunk.content)} > {MAX_CHUNK_SIZE}): "
                f"section={chunk.section!r}"
            )

    def test_no_empty_chunks(self):
        """No chunk should be empty or below the discard threshold."""
        for i, chunk in enumerate(self.chunks):
            assert len(chunk.content.strip()) >= CHUNK_DISCARD_LENGTH, (
                f"Chunk {i} is too short ({len(chunk.content.strip())} chars)"
            )

    # -- semantic integrity ------------------------------------------------

    def test_every_chunk_contains_dankbar(self):
        """Each day-entry has a ``j-gratitude`` block containing 'dankbar'.

        If chunks align with day boundaries, every chunk must contain
        the word 'dankbar' (from the ``Dafür bin ich dankbar`` callout).
        """
        for i, chunk in enumerate(self.chunks):
            assert "dankbar" in chunk.content.lower(), (
                f"Chunk {i} (section={chunk.section!r}) is missing 'dankbar' — "
                f"likely a day-entry was split mid-callout"
            )

    def test_no_chunk_mixes_multiple_dates(self):
        """No single chunk should contain entries from more than one day.

        Each day-entry starts with a ``> [!j-header] <Weekday>, DD.MM.YYYY``
        line.  If chunking respects ``---`` boundaries, each chunk should
        reference at most one *unique* date.  (The same date may appear
        twice — once in the context prefix and once in the callout body.)
        """
        for i, chunk in enumerate(self.chunks):
            unique_dates = set(_DATE_RE.findall(chunk.content))
            assert len(unique_dates) <= 1, (
                f"Chunk {i} mixes {len(unique_dates)} dates: {unique_dates} — "
                f"chunk boundaries don't align with day separators"
            )

    # -- section names -----------------------------------------------------

    def test_section_names_are_not_all_identical(self):
        """Section names should vary (e.g. contain the date), not all be
        the generic filename stem ``'Erfolgsjournal'``."""
        sections = {chunk.section for chunk in self.chunks}
        assert len(sections) > 1, (
            f"All {len(self.chunks)} chunks share the same section name: {sections}"
        )

    def test_section_names_contain_date_or_weekday(self):
        """Each section name should contain recognisable date information."""
        date_pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}")
        for i, chunk in enumerate(self.chunks):
            assert date_pattern.search(chunk.section), (
                f"Chunk {i} section={chunk.section!r} has no date — "
                f"section names should be derived from j-header callouts"
            )

    # -- chunk count -------------------------------------------------------

    def test_chunk_count_approximates_day_entries(self):
        """The number of chunks should be close to the number of day-entries.

        A tolerance of ±30% accounts for very short entries that get merged
        or very long entries that get split further.
        """
        lo = int(self.day_count * 0.7)
        hi = int(self.day_count * 1.3)
        assert lo <= len(self.chunks) <= hi, (
            f"Expected ~{self.day_count} chunks (days), got {len(self.chunks)} "
            f"(acceptable range: {lo}–{hi})"
        )


# ---------------------------------------------------------------------------
# Low-level splitter unit tests
# ---------------------------------------------------------------------------


class TestRecursiveSplit:
    """Unit tests for the recursive splitting primitives."""

    def test_short_text_stays_intact(self):
        assert _recursive_split("short", MAX_CHUNK_SIZE) == ["short"]

    def test_paragraph_boundary_respected(self):
        a = "A" * 800
        b = "B" * 800
        pieces = _recursive_split(f"{a}\n\n{b}", MAX_CHUNK_SIZE)
        assert len(pieces) == 2
        assert pieces[0].strip() == a
        assert pieces[1].strip() == b

    def test_thematic_break_split(self):
        a = "A" * 800
        b = "B" * 800
        pieces = _recursive_split(f"{a}\n---\n{b}", MAX_CHUNK_SIZE)
        assert all(len(p) <= MAX_CHUNK_SIZE for p in pieces)
        assert len(pieces) >= 2

    def test_all_pieces_within_max_size(self):
        huge = "X" * (MAX_CHUNK_SIZE * 3)
        pieces = _recursive_split(huge, MAX_CHUNK_SIZE)
        for p in pieces:
            assert len(p) <= MAX_CHUNK_SIZE


class TestMergeSplits:
    """Unit tests for the greedy merge helper."""

    def test_empty_parts_filtered(self):
        merged = _merge_splits(["", "a", "", "b", ""], 100, "\n")
        assert merged == ["a\nb"]

    def test_parts_exceeding_max_stay_separate(self):
        merged = _merge_splits(["a" * 10, "b" * 10], 8, "\n")
        assert len(merged) == 2

    def test_merge_respects_max_size(self):
        merged = _merge_splits(["aaa", "bbb", "ccc"], 7, "\n")
        for m in merged:
            assert len(m) <= 7


class TestHardSplit:
    """Unit tests for the hard-split fallback."""

    def test_overlap_equals_max_size_terminates(self):
        result = _hard_split("Hello World", 5, 5)
        assert all(len(p) <= 5 for p in result)

    def test_overlap_greater_than_max_size_terminates(self):
        result = _hard_split("Hello World", 5, 10)
        assert all(len(p) <= 5 for p in result)

    def test_zero_max_size_returns_full_text(self):
        assert _hard_split("Hello", 0, 0) == ["Hello"]

    def test_empty_text(self):
        assert _hard_split("", 5, 2) == []


class TestMakeChunk:
    """Unit tests for the chunk factory helper."""

    def test_context_prefix_includes_section(self):
        chunk = _make_chunk("notes/test.md", "My Section", "body")
        assert "test > My Section" in chunk.content

    def test_same_section_as_stem_no_duplication(self):
        chunk = _make_chunk("notes/test.md", "test", "body")
        assert "test > test" not in chunk.content

    def test_hash_is_sha256(self):
        chunk = _make_chunk("f.md", "s", "text")
        assert len(chunk.content_hash) == 64


class TestResolveWikilinks:
    """Unit tests for Obsidian wikilink resolution."""

    def test_simple_link(self):
        assert resolve_wikilinks("[[Note]]") == "Note"

    def test_aliased_link(self):
        assert resolve_wikilinks("[[Note|Display]]") == "Display"

    def test_path_link(self):
        assert resolve_wikilinks("[[Path/Note]]") == "Path/Note"


# ---------------------------------------------------------------------------
# Regression: standard Markdown-header files must not be affected
# ---------------------------------------------------------------------------


class TestHeaderBasedFileRegression:
    """Ensure files WITH Markdown headers still use header-based splitting,
    not the thematic-break fallback."""

    def test_sections_split_by_headers(self, fixtures_dir: Path):
        chunks = parse_markdown("SampleWithHeaders.md", str(fixtures_dir))
        sections = {c.section for c in chunks}
        # Must contain the header-derived section names, not a generic stem
        assert "First Section" in sections
        assert "Second Section" in sections
        assert "Third Section" in sections

    def test_no_chunk_named_after_stem_only(self, fixtures_dir: Path):
        chunks = parse_markdown("SampleWithHeaders.md", str(fixtures_dir))
        # The stem-only section ("SampleWithHeaders") is allowed for the
        # intro before the first header, but the majority should be named.
        named = [c for c in chunks if c.section != "SampleWithHeaders"]
        assert len(named) >= 3


# ---------------------------------------------------------------------------
# Unit test for _split_by_thematic_breaks
# ---------------------------------------------------------------------------


class TestSplitByThematicBreaks:
    """Direct tests for the thematic-break fallback splitter."""

    def test_no_breaks_returns_single_section(self):
        result = _split_by_thematic_breaks("plain text", "default")
        assert len(result) == 1
        assert result[0] == ("default", "plain text")

    def test_splits_at_hr(self):
        content = "block one\n---\nblock two\n---\nblock three"
        result = _split_by_thematic_breaks(content, "d")
        assert len(result) == 3

    def test_extracts_callout_header_as_section(self):
        content = (
            "> [!j-header] Montag, 01.01.2026\ncontent a"
            "\n---\n"
            "> [!j-header] Dienstag, 02.01.2026\ncontent b"
        )
        result = _split_by_thematic_breaks(content, "d")
        assert result[0][0] == "Montag, 01.01.2026"
        assert result[1][0] == "Dienstag, 02.01.2026"

    def test_fallback_to_numbered_sections(self):
        content = "block A\n---\nblock B"
        result = _split_by_thematic_breaks(content, "note")
        assert result[0][0] == "note 1"
        assert result[1][0] == "note 2"

    def test_empty_blocks_are_skipped(self):
        content = "block A\n---\n\n---\nblock B"
        result = _split_by_thematic_breaks(content, "d")
        bodies = [body for _, body in result]
        assert "" not in bodies
        assert len(result) == 2





"""Markdown parser with Obsidian-specific features (wikilinks, frontmatter, recursive chunking)."""

import re
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from .config import CHUNK_MIN_LENGTH, CHUNK_DISCARD_LENGTH, MAX_CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A semantic chunk extracted from a Markdown file."""

    file_path: str  # relative to vault root
    section: str  # header text or filename stem
    content: str  # plain text content
    content_hash: str  # SHA-256 of content


def resolve_wikilinks(text: str) -> str:
    """Replace Obsidian ``[[Link|Display]]`` → Display, ``[[Link]]`` → Link."""
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text


# Matches [[Note]], [[Note|Alias]], [[Note#Heading]], [[Note#Heading|Alias]]
# The negative lookbehind (?<!!) skips embedded links like ![[image.png]]
_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#\n]+)(?:[#|][^\]]*)?\]\]")

# Inline Obsidian tags: #tag or #tag/subtag – must start with a letter
# Negative lookbehind avoids matching markdown headings (# Heading at line start)
_TAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_/\-]*)")


def extract_wikilinks(text: str) -> list[str]:
    """Return all wikilink targets from *text* (note names, no section/alias).

    Embedded links (``![[...]]``) are excluded.
    """
    targets = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        if target:
            targets.append(target)
    return targets


def extract_tags(raw_text: str) -> list[str]:
    """Return all Obsidian tags from *raw_text* (frontmatter + inline).

    Handles both YAML frontmatter ``tags: [a, b]`` and inline ``#tag`` syntax.
    Tag names are normalised to lowercase without the leading ``#``.
    """
    tags: set[str] = set()

    # 1) Frontmatter tags field
    try:
        post = frontmatter.loads(raw_text)
        fm_tags = post.metadata.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        for t in fm_tags or []:
            if t:
                tags.add(str(t).strip().lower().lstrip("#"))
    except Exception:
        pass

    # 2) Inline #tag occurrences (covers both frontmatter section and body)
    for m in _TAG_RE.finditer(raw_text):
        tags.add(m.group(1).lower())

    return list(tags)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _with_context(file_path: str, section: str, body: str) -> str:
    """Prepend file path and section so the embedding captures topic context."""
    header = Path(file_path).stem
    if section and section != header:
        header = f"{header} > {section}"
    return f"{header}\n\n{body}"


def _make_chunk(file_path: str, section: str, text: str) -> Chunk:
    """Create a ``Chunk`` with context-enriched content and a content hash.

    Centralises the chunk-creation pattern that was previously duplicated in
    ``parse_markdown`` (small-file, recursive-split, and fallback paths).
    """
    enriched = _with_context(file_path, section, text)
    return Chunk(
        file_path=file_path,
        section=section,
        content=enriched,
        content_hash=_sha256(text),
    )


def parse_markdown(file_path: str, vault_path: str) -> list[Chunk]:
    """Parse a single Markdown file into chunks using recursive splitting.

    Splitting hierarchy (each level only if the chunk is still too large):
      1. ``#`` / ``##`` / ``###`` headers  (strongest semantic boundary)
      2. ``---`` thematic breaks            (explicit author-intended separator)
      3. ``\\n\\n`` paragraph breaks         (natural text boundary)
      4. ``\\n`` line breaks                 (last meaningful boundary)
      5. Hard cut at ``MAX_CHUNK_SIZE`` with ``CHUNK_OVERLAP`` overlap

    Files shorter than ``CHUNK_MIN_LENGTH`` become a single chunk.
    Chunks shorter than ``CHUNK_DISCARD_LENGTH`` are discarded.
    """
    full_path = Path(vault_path) / file_path

    # --- read & preprocess ------------------------------------------------
    try:
        post = frontmatter.load(str(full_path))
        content = post.content
    except Exception:
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            return []

    content = resolve_wikilinks(content)

    if not content or not content.strip():
        return []

    stem = Path(file_path).stem

    # --- small file → single chunk ----------------------------------------
    if len(content) < CHUNK_MIN_LENGTH:
        text = content.strip()
        if len(text) < CHUNK_DISCARD_LENGTH:
            return []
        return [_make_chunk(file_path, stem, text)]

    # --- Phase 1: split by headers into (section, body) pairs -------------
    sections = _split_by_headers(content, stem)

    # Fallback: if no Markdown headers were found and the single section is
    # oversized, try splitting at ``---`` thematic breaks instead.  This
    # handles Obsidian callout-based documents (e.g. Erfolgsjournal) that
    # use ``---`` as day separators with ``> [!j-header]`` callouts.
    if len(sections) == 1 and len(sections[0][1]) > MAX_CHUNK_SIZE:
        thematic = _split_by_thematic_breaks(content, stem)
        if len(thematic) > 1:
            sections = thematic

    # --- Phase 2: recursively split oversized sections --------------------
    chunks: list[Chunk] = []
    for section, body in sections:
        for piece in _recursive_split(body, MAX_CHUNK_SIZE):
            text = piece.strip()
            if len(text) < CHUNK_DISCARD_LENGTH:
                continue
            chunks.append(_make_chunk(file_path, section, text))

    # Fallback: if all pieces were discarded, keep the whole content as one chunk
    if not chunks:
        text = content.strip()
        if len(text) >= CHUNK_DISCARD_LENGTH:
            chunks.append(_make_chunk(file_path, stem, text))

    return chunks


def _split_by_headers(content: str, default_section: str) -> list[tuple[str, str]]:
    """Split *content* at ``#``/``##``/``###`` headers.

    Returns a list of ``(section_name, body_text)`` tuples.
    If there are no headers the entire content is returned under *default_section*.
    """
    parts = re.split(r"^(#{1,3}\s+.+)$", content, flags=re.MULTILINE)

    sections: list[tuple[str, str]] = []
    current_header = default_section
    current_body = ""

    for part in parts:
        if re.match(r"^#{1,3}\s+", part):
            if current_body.strip():
                sections.append((current_header, current_body.strip()))
            current_header = part.strip().lstrip("#").strip()
            current_body = part + "\n"
        else:
            current_body += part

    if current_body.strip():
        sections.append((current_header, current_body.strip()))

    return sections


# Matches the Obsidian callout header used in Erfolgsjournal-style documents.
# Example: ``> [!j-header] Montag, 21.12.2025``
_CALLOUT_HEADER_RE = re.compile(
    r">\s*\[!j-header\]\s*(.+)", re.IGNORECASE
)


def _split_by_thematic_breaks(
    content: str, default_section: str,
) -> list[tuple[str, str]]:
    """Split *content* at ``---`` thematic breaks.

    This is the fallback for documents without Markdown headers (``#``/``##``)
    that use ``---`` as semantic separators — for example Obsidian journals
    built with callout blocks.

    Section names are extracted from ``> [!j-header] …`` callouts if present,
    otherwise numbered as ``<default_section> 1``, ``<default_section> 2``, etc.

    Returns a list of ``(section_name, body_text)`` tuples.
    """
    # Split at lines that consist solely of ``---`` (with optional whitespace)
    blocks = re.split(r"\n-{3,}\n", content)

    if len(blocks) <= 1:
        return [(default_section, content.strip())]

    sections: list[tuple[str, str]] = []
    for idx, block in enumerate(blocks, start=1):
        body = block.strip()
        if not body:
            continue

        # Try to extract a meaningful section name from a callout header
        m = _CALLOUT_HEADER_RE.search(body)
        section = m.group(1).strip() if m else f"{default_section} {idx}"

        sections.append((section, body))

    return sections or [(default_section, content.strip())]


# Ordered from strongest to weakest boundary.
# Each entry is a regex that matches the separator (kept out of the chunks).
_SECONDARY_SEPARATORS: list[re.Pattern] = [
    re.compile(r"\n---\n"),   # thematic break
    re.compile(r"\n\n"),      # paragraph break
    re.compile(r"\n"),        # line break
]


def _recursive_split(text: str, max_size: int) -> list[str]:
    """Recursively split *text* so every piece is ≤ *max_size* chars.

    Tries separators from strongest to weakest.  Falls back to a hard cut
    with ``CHUNK_OVERLAP`` overlap when no separator can reduce the size.
    """
    if len(text) <= max_size:
        return [text]

    for sep in _SECONDARY_SEPARATORS:
        parts = sep.split(text)
        if len(parts) > 1:
            # Reassemble into chunks that stay within max_size
            merged = _merge_splits(parts, max_size, sep.pattern.replace("\\n", "\n"))
            if all(len(m) <= max_size for m in merged):
                return merged
            # Some pieces are still too large → recurse on those
            result: list[str] = []
            for piece in merged:
                result.extend(_recursive_split(piece, max_size))
            return result

    # No separator worked → hard cut with overlap
    return _hard_split(text, max_size, CHUNK_OVERLAP)


def _merge_splits(parts: list[str], max_size: int, join_str: str) -> list[str]:
    """Greedily merge consecutive *parts* as long as they fit within *max_size*."""
    merged: list[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        candidate = (current + join_str + part) if current else part
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                merged.append(current)
            current = part

    if current:
        merged.append(current)

    return merged


def _hard_split(text: str, max_size: int, overlap: int) -> list[str]:
    """Split *text* at exact character boundaries with *overlap*.

    The effective overlap is clamped to ``max_size - 1`` so the cursor always
    advances by at least one character (prevents infinite loops).
    """
    if max_size <= 0:
        return [text] if text else []
    # Ensure progress: overlap must be strictly less than max_size
    safe_overlap = min(overlap, max_size - 1)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_size
        pieces.append(text[start:end])
        start = end - safe_overlap
    return pieces


def parse_pdf(file_path: str, vault_path: str) -> list[Chunk]:
    """Extract text from a PDF file, splitting long pages recursively.

    Requires ``pypdf`` (already in requirements.txt).
    Pages with too little text are discarded.
    """
    from pypdf import PdfReader  # local import so missing dep fails loudly

    full_path = Path(vault_path) / file_path
    try:
        reader = PdfReader(str(full_path))
    except Exception as exc:
        logger.warning("Cannot read PDF %s: %s", file_path, exc)
        return []

    chunks: list[Chunk] = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            continue
        if len(text) < CHUNK_DISCARD_LENGTH:
            continue
        section = f"page_{page_num}"
        for piece in _recursive_split(text, MAX_CHUNK_SIZE):
            piece = piece.strip()
            if len(piece) < CHUNK_DISCARD_LENGTH:
                continue
            chunks.append(_make_chunk(file_path, section, piece))

    logger.debug("parse_pdf %s → %d chunks", file_path, len(chunks))
    return chunks


"""Markdown parser with Obsidian-specific features (wikilinks, frontmatter, header chunking)."""

import re
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from .config import CHUNK_MIN_LENGTH, CHUNK_DISCARD_LENGTH

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


def parse_markdown(file_path: str, vault_path: str) -> list[Chunk]:
    """Parse a single Markdown file into chunks.

    * Files shorter than ``CHUNK_MIN_LENGTH`` become a single chunk.
    * Longer files are split at ``#``/``##``/``###`` headers.
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
        enriched = _with_context(file_path, stem, text)
        return [
            Chunk(
                file_path=file_path,
                section=stem,
                content=enriched,
                content_hash=_sha256(text),
            )
        ]

    # --- split by headers -------------------------------------------------
    #  re.split keeps the delimiters as separate list items when using a
    #  capturing group.  We recombine header + body into chunks.
    parts = re.split(r"^(#{1,3}\s+.+)$", content, flags=re.MULTILINE)

    chunks: list[Chunk] = []
    current_header = stem
    current_body = ""

    for part in parts:
        if re.match(r"^#{1,3}\s+", part):
            # flush previous chunk
            if current_body.strip():
                text = current_body.strip()
                if len(text) >= CHUNK_DISCARD_LENGTH:
                    enriched = _with_context(file_path, current_header, text)
                    chunks.append(
                        Chunk(
                            file_path=file_path,
                            section=current_header,
                            content=enriched,
                            content_hash=_sha256(text),
                        )
                    )
            current_header = part.strip().lstrip("#").strip()
            current_body = part + "\n"
        else:
            current_body += part

    # last chunk
    if current_body.strip():
        text = current_body.strip()
        if len(text) >= CHUNK_DISCARD_LENGTH:
            enriched = _with_context(file_path, current_header, text)
            chunks.append(
                Chunk(
                    file_path=file_path,
                    section=current_header,
                    content=enriched,
                    content_hash=_sha256(text),
                )
            )

    return chunks or (
        [Chunk(
            file_path=file_path,
            section=stem,
            content=_with_context(file_path, stem, content.strip()),
            content_hash=_sha256(content.strip()),
        )]
        if len(content.strip()) >= CHUNK_DISCARD_LENGTH
        else []
    )


def parse_pdf(file_path: str, vault_path: str) -> list[Chunk]:
    """Extract text from a PDF file, one chunk per page.

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
        enriched = _with_context(file_path, section, text)
        chunks.append(
            Chunk(
                file_path=file_path,
                section=section,
                content=enriched,
                content_hash=_sha256(text),
            )
        )

    logger.debug("parse_pdf %s → %d chunks", file_path, len(chunks))
    return chunks


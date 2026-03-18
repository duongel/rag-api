"""FastAPI REST API for the RAG API."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Security, status as http_status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from typing import Optional

from urllib.parse import quote

from .config import (
    API_BEARER_TOKEN,
    AUTH_REQUIRED,
    PUBLIC_URL,
    PAPERLESS_PUBLIC_URL,
    DATA_SOURCES,
)

logger = logging.getLogger(__name__)

# SKILL.md is copied into /app/ by the Dockerfile; fall back to repo root for local dev
_SKILL_PATH = next(
    (p for p in [Path("/app/SKILL.md"), Path(__file__).parents[2] / "SKILL.md"] if p.exists()),
    None,
)

app = FastAPI(
    title="RAG API",
    description=(
        "Local RAG search over an Obsidian vault and Paperless-NGX documents. "
        "Supports semantic search with graph-boosted ranking (wikilinks, backlinks, tags) "
        "and exact keyword search. "
        f"Fetch the full agent skill at {PUBLIC_URL}/skill"
    ),
    version="2.0.0",
    servers=[{"url": PUBLIC_URL, "description": "RAG API"}],
)

# Injected at startup by main.py
indexer = None  # type: ignore[assignment]
searcher = None  # type: ignore[assignment]
indexing_status: dict = {"indexing": True, "indexed_files": 0, "total_files": 0}
_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """Protect data-bearing endpoints when running outside a trusted local setup."""
    if not AUTH_REQUIRED:
        return

    if not API_BEARER_TOKEN:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but API_BEARER_TOKEN is not configured.",
        )

    if credentials is None or credentials.credentials != API_BEARER_TOKEN:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── request / response models ────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    expand_links: bool = True
    min_score: float = 0.0  # filter results below this threshold
    sort_by_date: bool = False  # sort results newest-first instead of by score
    paperless_tags: Optional[list[str]] = None
    paperless_correspondent: Optional[str] = None
    paperless_created_year: Optional[int] = None


class SearchResult(BaseModel):
    file_path: str
    section: str = ""
    content: str
    score: float = 0.0
    match_type: str = ""
    source: str = "obsidian"  # "obsidian" | "paperless"
    source_url: str = ""  # direct link to the document; empty when no public URL is configured
    created: str = ""  # ISO date from Paperless; empty for Obsidian notes


class SearchResponse(BaseModel):
    results: list[SearchResult]
    count: int


class NoteResponse(BaseModel):
    file_path: str
    content: str


class NoteRequest(BaseModel):
    path: str


class StatsResponse(BaseModel):
    total_chunks: int
    total_files: int
    obsidian_files: int
    paperless_files: int
    link_graph_edges: int


class StatusResponse(BaseModel):
    indexing: bool
    indexed_files: int
    total_files: int
    obsidian_indexed: int = 0
    obsidian_total: int = 0
    paperless_indexed: int = 0
    paperless_total: int = 0


class ReindexResponse(BaseModel):
    updated_files: int
    message: str


# ── helpers ──────────────────────────────────────────────────────────────

def _enrich_source_url(result: dict) -> dict:
    """Add a source_url to a result dict so callers can jump directly to the document."""
    source = result.get("source", "obsidian")
    file_path = result.get("file_path", "")
    if source == "paperless" and PAPERLESS_PUBLIC_URL:
        doc_id = result.get("paperless_doc_id", "")
        if not doc_id:
            # Fallback: numeric filename IS the document ID
            stem = Path(file_path).stem
            if stem.isdigit():
                doc_id = stem
        if doc_id:
            result["source_url"] = (
                f"{PAPERLESS_PUBLIC_URL.rstrip('/')}/documents/{int(doc_id)}/document"
            )
    elif source == "obsidian":
        result["source_url"] = (
            f"{PUBLIC_URL.rstrip('/')}/note?path={quote(file_path)}"
        )
    return result


# ── endpoints ────────────────────────────────────────────────────────────


@app.get("/skill", response_class=PlainTextResponse, include_in_schema=False)
def get_skill():
    """Returns the agent skill documentation as Markdown (for linking to agents)."""
    if _SKILL_PATH is None:
        raise HTTPException(status_code=404, detail="SKILL.md not found")
    content = _SKILL_PATH.read_text(encoding="utf-8")
    content = content.replace("http://127.0.0.1:8484", PUBLIC_URL)
    content = content.replace("http://localhost:8484", PUBLIC_URL)
    return PlainTextResponse(content, media_type="text/markdown")


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse, summary="Indexing status")
def status(_: None = Security(require_auth)):
    """Returns whether the background indexing is still running and how many files are indexed so far."""
    return indexing_status


@app.get("/stats", response_model=StatsResponse, summary="Vault statistics")
def stats(_: None = Security(require_auth)):
    """Total chunks, files, and number of wikilink edges in the graph."""
    return indexer.get_stats()


@app.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search",
    description=(
        "Embeds the query and returns the most similar note chunks. "
        "Results are graph-boosted: notes connected via wikilinks, backlinks, or shared tags "
        "are ranked higher when they are strongly linked to top semantic matches.\n\n"
        "`match_type` values: `semantic` | `link_1` | `backlink` | `tag` | `link_2`\n\n"
        "**Paperless filters:** pass `paperless_tags`, `paperless_correspondent`, or "
        "`paperless_created_year` to filter by metadata stored in ChromaDB before semantic ranking.\n\n"
        "**`sort_by_date`:** when true, results are sorted newest-first by creation date "
        "instead of by score. Useful for queries like 'letzte Rechnung'.\n\n"
        "**Use for:** conceptual questions, topics, explanations.\n\n"
        "**Do NOT use for:** abbreviations, URLs, exact class/enum names \u2192 use `/keyword-search`.\n\n"
        "Set `min_score: 0.70` to suppress low-confidence results."
    ),
)
def search(req: SearchRequest, _: None = Security(require_auth)):
    """Semantic similarity search across all indexed notes."""
    results = searcher.semantic_search(
        req.query, req.top_k, req.expand_links,
        paperless_tags=req.paperless_tags,
        paperless_correspondent=req.paperless_correspondent,
        paperless_created_year=req.paperless_created_year,
        sort_by_date=req.sort_by_date,
    )
    if req.min_score > 0:
        results = [r for r in results if r["score"] >= req.min_score]
    results = [_enrich_source_url(r) for r in results]
    return SearchResponse(results=results, count=len(results))


@app.post(
    "/keyword-search",
    response_model=SearchResponse,
    summary="Keyword search",
    description=(
        "Case-insensitive text search across filenames and note content.\n\n"
        "**Multi-word queries** use AND logic: every word must appear in the document.\n\n"
        "**Use for:** abbreviations (`VPN`, `NVR`, `PoE`), hostnames (`homeassistant`, `pihole`), "
        "IP addresses, port numbers, model names (`USG-3P`), version strings (`v3.2.1`), "
        "config keys (`VAULT_PATH`), class names, enum values, "
        "or any query where the exact string must appear in the note.\n\n"
        "**Do NOT use for:** conceptual questions, topics, explanations → use `/search`."
    ),
)
def keyword_search(req: SearchRequest, _: None = Security(require_auth)):
    """Exact keyword search in filenames and note content."""
    results = searcher.keyword_search(
        req.query, req.top_k,
        paperless_tags=req.paperless_tags,
        paperless_correspondent=req.paperless_correspondent,
        paperless_created_year=req.paperless_created_year,
    )
    results = [_enrich_source_url(r) for r in results]
    return SearchResponse(results=results, count=len(results))


@app.post(
    "/hybrid-search",
    response_model=SearchResponse,
    summary="Hybrid search (semantic + keyword)",
    description=(
        "Runs both semantic and keyword search, merges results and deduplicates.\n\n"
        "Best for natural-language queries that contain specific identifiers, "
        "e.g. 'Kaufvertrag Grundstück Montabaur' or 'Rechnung Audi e-tron 2025'.\n\n"
        "Results are ranked by score (highest first) unless `sort_by_date: true` is set.\n\n"
        "Supports all Paperless filters and `min_score` threshold."
    ),
)
def hybrid_search(req: SearchRequest, _: None = Security(require_auth)):
    """Combined semantic + keyword search with deduplication."""
    results = searcher.hybrid_search(
        req.query, req.top_k,
        paperless_tags=req.paperless_tags,
        paperless_correspondent=req.paperless_correspondent,
        paperless_created_year=req.paperless_created_year,
        sort_by_date=req.sort_by_date,
        min_score=req.min_score,
    )
    results = [_enrich_source_url(r) for r in results]
    return SearchResponse(results=results, count=len(results))


@app.get(
    "/note",
    response_model=NoteResponse,
    summary="Get full note",
    description="Returns the complete raw Markdown content of a single note by its relative vault path.",
)
def get_note(
    path: str = Query(..., description="Relative path to the note, e.g. Projects/Home/Heating.md"),
    _: None = Security(require_auth),
):
    """Return the full Markdown content of a single note."""
    result = searcher.get_note(path)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")
    return result


@app.post(
    "/note",
    response_model=NoteResponse,
    summary="Get full note (POST)",
    description="Same as GET /note but accepts the path in a JSON body. Useful for clients that use POST for all endpoints.",
)
def post_note(req: NoteRequest, _: None = Security(require_auth)):
    """Return the full Markdown content of a single note (POST variant)."""
    result = searcher.get_note(req.path)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Note not found: {req.path}")
    return result


@app.post("/reindex", response_model=ReindexResponse, summary="Trigger full reindex")
def reindex(_: None = Security(require_auth)):
    """Re-scans the vault and Paperless archive (if configured) and updates changed files."""
    global indexing_status
    indexing_status = {"indexing": True, "indexed_files": 0, "total_files": 0}
    count = 0
    if DATA_SOURCES in ("obsidian", "all"):
        count += indexer.full_reindex()
    if DATA_SOURCES in ("paperless", "all"):
        count += indexer.full_reindex(source="paperless")
    indexing_status = {"indexing": False, "indexed_files": len(indexer._file_hashes), "total_files": len(indexer._file_hashes)}
    return ReindexResponse(updated_files=count, message=f"Reindexed {count} files")


# ── Paperless webhook ────────────────────────────────────────────────────


class PaperlessWebhookPayload(BaseModel):
    document_id: int
    action: str = ""  # "added", "updated", "deleted"


@app.post("/webhook/paperless", summary="Paperless document webhook", include_in_schema=False)
def paperless_webhook(payload: PaperlessWebhookPayload, _: None = Security(require_auth)):
    """Receives notifications from Paperless when documents change.

    The webhook is auto-registered at startup so no manual configuration
    is needed.  Accepts ``{"document_id": 123, "action": "added"}`` etc.
    """
    doc_id = payload.document_id
    action = payload.action.lower()

    if action == "deleted":
        indexer.remove_paperless_doc(doc_id)
        logger.info("Webhook: removed paperless doc %d", doc_id)
        return {"status": "removed", "document_id": doc_id}

    # added / updated / unknown → (re-)index
    try:
        updated = indexer.reindex_paperless_doc(doc_id)
    except Exception:
        logger.exception("Webhook: failed to reindex paperless doc %d", doc_id)
        return JSONResponse(
            status_code=502,
            content={"status": "error", "document_id": doc_id},
        )
    logger.info("Webhook: %s paperless doc %d (updated=%s)", action or "reindex", doc_id, updated)
    return {"status": "indexed" if updated else "unchanged", "document_id": doc_id}

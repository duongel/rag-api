"""Entry-point: waits for Ollama, indexes vault in background, starts watcher + API."""

import logging
import threading
import time
import secrets
from pathlib import Path

import requests
import uvicorn

from .config import (
    OLLAMA_URL, EMBED_MODEL, API_PORT, AUTH_REQUIRED, API_BEARER_TOKEN,
    OLLAMA_TIMEOUT_SECONDS,
    DATA_SOURCES, PAPERLESS_ARCHIVE_PATH, VAULT_PATH,
)
from .indexer import Indexer
from .search import Searcher
from .watcher import start_watcher
from . import api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_INDEX_OBSIDIAN = DATA_SOURCES in ("obsidian", "all")
_INDEX_PAPERLESS = DATA_SOURCES in ("paperless", "all") and bool(PAPERLESS_ARCHIVE_PATH)


def _wait_for_ollama():
    """Block until Ollama is reachable and the embedding model is available."""
    logger.info("Waiting for Ollama at %s …", OLLAMA_URL)
    started = time.monotonic()
    last_error = ""
    last_models: list[str] = []
    while True:
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if resp.ok:
                last_models = [m["name"] for m in resp.json().get("models", [])]
                if any(EMBED_MODEL in m for m in last_models):
                    logger.info("Ollama ready – model '%s' available.", EMBED_MODEL)
                    return
                logger.info(
                    "Model '%s' not yet available. Available: %s – retrying …",
                    EMBED_MODEL,
                    last_models,
                )
                last_error = f"model '{EMBED_MODEL}' missing"
        except Exception as exc:
            last_error = str(exc)

        if time.monotonic() - started >= OLLAMA_TIMEOUT_SECONDS:
            detail = last_error or "unknown error"
            available = f" Available models: {last_models}." if last_models else ""
            raise RuntimeError(
                f"Ollama at {OLLAMA_URL} did not become ready within "
                f"{OLLAMA_TIMEOUT_SECONDS}s ({detail}).{available}"
            )
        time.sleep(5)


def main():
    if AUTH_REQUIRED and not API_BEARER_TOKEN:
        raise RuntimeError(
            "AUTH_REQUIRED is enabled but API_BEARER_TOKEN is empty. "
            f"Set a long random bearer token, for example: {secrets.token_hex(32)}"
        )
    if _INDEX_OBSIDIAN and not Path(VAULT_PATH).exists():
        raise RuntimeError(
            f"Obsidian indexing is enabled but VAULT_PATH does not exist in the container: {VAULT_PATH}"
        )

    logger.info("Data sources: %s (paperless archive: %s)", DATA_SOURCES, PAPERLESS_ARCHIVE_PATH or "not configured")
    _wait_for_ollama()

    logger.info("Initialising indexer …")
    indexer = Indexer()
    search = Searcher(indexer)

    # inject into FastAPI module
    api.indexer = indexer
    api.searcher = search
    api.indexing_status = {
        "indexing": _INDEX_OBSIDIAN or _INDEX_PAPERLESS,
        "indexed_files": 0,
        "total_files": 0,
        "obsidian_indexed": 0,
        "obsidian_total": 0,
        "paperless_indexed": 0,
        "paperless_total": 0,
    }

    def _on_progress(processed: int, total: int, source: str) -> None:
        api.indexing_status[f"{source}_indexed"] = processed
        api.indexing_status[f"{source}_total"] = total
        api.indexing_status["indexed_files"] = (
            api.indexing_status["obsidian_indexed"]
            + api.indexing_status["paperless_indexed"]
        )
        api.indexing_status["total_files"] = (
            api.indexing_status["obsidian_total"]
            + api.indexing_status["paperless_total"]
        )

    def _run_reindex():
        try:
            if _INDEX_OBSIDIAN:
                indexer.full_reindex(
                    on_progress=lambda p, t: _on_progress(p, t, "obsidian")
                )
            if _INDEX_PAPERLESS:
                logger.info("Starting Paperless archive reindex …")
                indexer.full_reindex(
                    base_path=PAPERLESS_ARCHIVE_PATH,
                    source="paperless",
                    on_progress=lambda p, t: _on_progress(p, t, "paperless"),
                )
        except Exception as e:
            logger.error("Reindex failed: %s", e)
        finally:
            api.indexing_status["indexing"] = False
            api.indexing_status["indexed_files"] = len(indexer._file_hashes)
            api.indexing_status["total_files"] = len(indexer._file_hashes)
            logger.info(
                "Indexing complete – %d files in index.", len(indexer._file_hashes)
            )

    threading.Thread(target=_run_reindex, daemon=True).start()

    logger.info("Starting file watcher …")
    observer = start_watcher(
        indexer,
        watch_obsidian=_INDEX_OBSIDIAN,
        watch_paperless=_INDEX_PAPERLESS,
    )

    logger.info("Starting API server on port %d …", API_PORT)
    try:
        uvicorn.run(api.app, host="0.0.0.0", port=API_PORT)
    finally:
        if observer:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()

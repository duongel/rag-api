"""Entry-point: waits for Ollama, indexes vault in background, starts watcher + API."""

import logging
import threading
import time
import secrets

import requests
import uvicorn

from .config import OLLAMA_URL, EMBED_MODEL, API_PORT, AUTH_REQUIRED, API_BEARER_TOKEN, DATA_SOURCES
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


def _wait_for_ollama():
    """Block until Ollama is reachable and the embedding model is available."""
    logger.info("Waiting for Ollama at %s …", OLLAMA_URL)
    while True:
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if resp.ok:
                models = [m["name"] for m in resp.json().get("models", [])]
                if any(EMBED_MODEL in m for m in models):
                    logger.info("Ollama ready – model '%s' available.", EMBED_MODEL)
                    return
                logger.info(
                    "Model '%s' not yet available. Available: %s – retrying …",
                    EMBED_MODEL,
                    models,
                )
        except Exception:
            pass
        time.sleep(5)


def main():
    if AUTH_REQUIRED and not API_BEARER_TOKEN:
        raise RuntimeError(
            "AUTH_REQUIRED is enabled but API_BEARER_TOKEN is empty. "
            f"Set a long random bearer token, for example: {secrets.token_hex(32)}"
        )

    logger.info("Data sources: %s", DATA_SOURCES)
    _wait_for_ollama()

    logger.info("Initialising indexer …")
    indexer = Indexer()
    search = Searcher(indexer)

    # inject into FastAPI module
    api.indexer = indexer
    api.searcher = search
    api.indexing_status = {"indexing": _INDEX_OBSIDIAN, "indexed_files": 0, "total_files": 0}

    def _on_progress(processed: int, total: int) -> None:
        api.indexing_status["indexed_files"] = processed
        api.indexing_status["total_files"] = total

    def _run_reindex():
        try:
            if _INDEX_OBSIDIAN:
                indexer.full_reindex(on_progress=_on_progress)
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

    observer = None
    if _INDEX_OBSIDIAN:
        logger.info("Starting file watcher …")
        observer = start_watcher(indexer)

    logger.info("Starting API server on port %d …", API_PORT)
    try:
        uvicorn.run(api.app, host="0.0.0.0", port=API_PORT)
    finally:
        if observer:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()

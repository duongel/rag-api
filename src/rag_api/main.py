"""Entry-point: waits for Ollama, indexes vault in background, starts watcher + API."""

import logging
import threading
import time
import secrets
from pathlib import Path
from typing import Optional

import requests
import uvicorn

from .config import (
    OLLAMA_URL, EMBED_MODEL, API_PORT, AUTH_REQUIRED, API_BEARER_TOKEN,
    OLLAMA_TIMEOUT_SECONDS,
    DATA_SOURCES, VAULT_PATH,
    PAPERLESS_URL, PAPERLESS_TOKEN, RAG_API_INTERNAL_URL,
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
_INDEX_PAPERLESS = DATA_SOURCES in ("paperless", "all") and bool(PAPERLESS_URL) and bool(PAPERLESS_TOKEN)


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


def _register_paperless_webhook():
    """Auto-register a consumption webhook in Paperless-NGX.

    Checks whether a webhook pointing to rag-api already exists.  If not,
    creates one so that document changes trigger real-time re-indexing.
    Runs best-effort — failures are logged but don't block startup.
    """
    webhook_url = f"{RAG_API_INTERNAL_URL.rstrip('/')}/webhook/paperless"

    # Include bearer token so Paperless can authenticate when AUTH_REQUIRED=true
    webhook_headers: dict[str, str] = {"Content-Type": "application/json"}
    if AUTH_REQUIRED and API_BEARER_TOKEN:
        webhook_headers["Authorization"] = f"Bearer {API_BEARER_TOKEN}"

    headers = {"Authorization": f"Token {PAPERLESS_TOKEN}"}
    try:
        # List existing consumption templates / webhooks
        # Paperless-NGX ≥2.x uses /api/share_links/ or custom scripts,
        # but the post-consume webhook is configured via /api/workflows/
        # Paginate through all workflow pages to avoid creating duplicates
        found_existing = False
        url: Optional[str] = f"{PAPERLESS_URL}/api/workflows/"
        while url:
            resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                logger.warning("Could not list Paperless workflows (HTTP %d) — skipping webhook registration", resp.status_code)
                return

            data = resp.json()
            for wf in data.get("results", []):
                if not wf.get("enabled", True):
                    continue
                for action in wf.get("actions", []):
                    if action.get("type") == "webhook" and action.get("webhook", {}).get("url") == webhook_url:
                        # Ensure headers (e.g. auth token) are up to date
                        existing_headers = action.get("webhook", {}).get("headers", {})
                        if existing_headers != webhook_headers:
                            logger.info("Updating webhook headers for workflow %d", wf["id"])
                            action["webhook"]["headers"] = webhook_headers
                            update_resp = requests.put(
                                f"{PAPERLESS_URL}/api/workflows/{wf['id']}/",
                                json=wf,
                                headers=headers,
                                timeout=10,
                            )
                            if update_resp.ok:
                                logger.info("Webhook headers updated successfully")
                            else:
                                logger.warning("Failed to update webhook headers (HTTP %d)", update_resp.status_code)
                            found_existing = True
                        else:
                            logger.info("Paperless webhook already registered (workflow %d)", wf["id"])
                            found_existing = True
            url = data.get("next")

        if found_existing:
            return

        # Create workflow for consumption events (add/update).
        # Paperless-NGX does not support deletion triggers, so deleted
        # documents are cleaned up during the next full reindex.
        workflow_data = {
            "name": "rag-api reindex",
            "enabled": True,
            "triggers": [
                {
                    "type": "consumption",
                    "sources": ["consume_folder", "api_upload", "mail_fetch"],
                    "filter_filename": "*",
                }
            ],
            "actions": [
                {
                    "type": "webhook",
                    "webhook": {
                        "url": webhook_url,
                        "use_params": False,
                        "params": {},
                        "body": '{"document_id": {document_id}, "action": "updated"}',
                        "headers": webhook_headers,
                    },
                }
            ],
        }
        resp = requests.post(
            f"{PAPERLESS_URL}/api/workflows/",
            json=workflow_data,
            headers=headers,
            timeout=10,
        )
        if resp.ok:
            logger.info("Registered Paperless webhook workflow → %s", webhook_url)
        else:
            logger.warning(
                "Failed to create Paperless webhook workflow (HTTP %d): %s",
                resp.status_code,
                resp.text[:200],
            )
    except Exception as e:
        logger.warning("Paperless webhook registration failed: %s", e)


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

    logger.info(
        "Data sources: %s (paperless API: %s)",
        DATA_SOURCES,
        PAPERLESS_URL or "not configured",
    )
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
                logger.info("Starting Paperless API reindex …")
                indexer.full_reindex(
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

    # Register Paperless webhook for real-time updates
    if _INDEX_PAPERLESS:
        threading.Thread(target=_register_paperless_webhook, daemon=True).start()

    # Only start filesystem watcher for Obsidian (Paperless uses webhooks now)
    logger.info("Starting file watcher …")
    observer = start_watcher(
        indexer,
        watch_obsidian=_INDEX_OBSIDIAN,
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

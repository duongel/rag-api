"""File watcher using PollingObserver (reliable on Docker-for-Mac bind mounts)."""

import logging
import threading
from pathlib import Path

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from .config import VAULT_PATH, POLL_INTERVAL
from .indexer import Indexer

logger = logging.getLogger(__name__)


class _ObsidianHandler(FileSystemEventHandler):
    """Debounced handler that re-indexes changed Markdown files."""

    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    # --- filtering --------------------------------------------------------

    @staticmethod
    def _should_ignore(rel_path: str) -> bool:
        """Return True for any path that must NOT trigger re-indexing.

        Ignored:
        - Any path component starting with '.'  (.obsidian/, .trash/, .hotreload, …)
        - Editor / OS temp files  (~file.md, file.md~, file.md.tmp)
        - Anything that is not a plain *.md file
        """
        parts = Path(rel_path).parts
        filename = parts[-1] if parts else ""

        # .obsidian/, .trash/, hidden files / dirs
        if any(p.startswith(".") for p in parts):
            return True

        # editor / sync temp files
        if filename.startswith("~") or filename.endswith("~"):
            return True

        # only *.md and *.pdf files trigger re-indexing
        if not (filename.endswith(".md") or filename.endswith(".pdf")):
            return True

        return False

    @staticmethod
    def _rel_path(src_path: str) -> str | None:
        try:
            return str(Path(src_path).relative_to(VAULT_PATH))
        except ValueError:
            return None

    # --- debounced processing ---------------------------------------------

    def _schedule(self, rel_path: str, deleted: bool = False):
        if self._should_ignore(rel_path):
            return
        with self._lock:
            prev = self._timers.pop(rel_path, None)
            if prev:
                prev.cancel()
            t = threading.Timer(3.0, self._process, args=(rel_path, deleted))
            self._timers[rel_path] = t
            t.start()

    def _process(self, rel_path: str, deleted: bool):
        try:
            if deleted:
                self.indexer.remove_file(rel_path)
                logger.info("Removed from index: %s", rel_path)
            else:
                self.indexer.index_file(rel_path)
        except Exception as e:
            logger.error("Error processing %s: %s", rel_path, e)

    # --- watchdog callbacks -----------------------------------------------

    def on_created(self, event):
        if event.is_directory:
            return
        rp = self._rel_path(event.src_path)
        if rp:
            self._schedule(rp)

    def on_modified(self, event):
        if event.is_directory:
            return
        rp = self._rel_path(event.src_path)
        if rp:
            self._schedule(rp)

    def on_deleted(self, event):
        if event.is_directory:
            return
        rp = self._rel_path(event.src_path)
        if rp:
            self._schedule(rp, deleted=True)

    def on_moved(self, event):
        if event.is_directory:
            return
        old = self._rel_path(event.src_path)
        new = self._rel_path(event.dest_path)
        if old:
            self._schedule(old, deleted=True)
        if new:
            self._schedule(new)


def start_watcher(indexer: Indexer) -> PollingObserver:
    """Start watching the entire vault directory. Returns the observer (call .stop() to shut down)."""
    observer = PollingObserver(timeout=POLL_INTERVAL)
    handler = _ObsidianHandler(indexer)

    vault_path = Path(VAULT_PATH)
    if vault_path.exists():
        observer.schedule(handler, str(vault_path), recursive=True)
        logger.info("Watching vault for changes.")
    else:
        logger.warning("Vault path does not exist.")

    observer.daemon = True
    observer.start()
    return observer

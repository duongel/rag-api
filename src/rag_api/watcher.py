"""File watcher for the Obsidian vault and the Paperless archive directory.

Observer selection (in priority order):
  1. WATCHER_POLLING=true  → PollingObserver  (forced; use for Docker Desktop on macOS)
  2. Linux, inotify available → InotifyObserver  (real kernel events, zero overhead)
  3. Fallback               → PollingObserver
"""

import logging
import platform
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler

from .config import VAULT_PATH, PAPERLESS_ARCHIVE_PATH, POLL_INTERVAL, WATCHER_POLLING
from .indexer import Indexer

logger = logging.getLogger(__name__)


def _is_docker_desktop() -> bool:
    """Return True when running inside Docker Desktop on macOS.

    Docker Desktop uses LinuxKit as its VM kernel; the release string contains
    'linuxkit' or 'docker-desktop'. Detecting this avoids forcing users to set
    WATCHER_POLLING=true manually.
    """
    try:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text().strip().lower()
        return "linuxkit" in osrelease or "docker-desktop" in osrelease
    except Exception:
        return False


def _make_observer():
    """Return the best available observer for the current platform."""
    if WATCHER_POLLING:
        logger.info("WATCHER_POLLING=true – using PollingObserver (interval: %ds)", POLL_INTERVAL)
        from watchdog.observers.polling import PollingObserver
        return PollingObserver(timeout=POLL_INTERVAL)
    if platform.system() == "Linux" and not _is_docker_desktop():
        try:
            from watchdog.observers.inotify import InotifyObserver
            logger.info("Using InotifyObserver (native Linux)")
            return InotifyObserver()
        except Exception:
            pass
    from watchdog.observers.polling import PollingObserver
    if _is_docker_desktop():
        logger.info("Docker Desktop detected – using PollingObserver (interval: %ds)", POLL_INTERVAL)
    return PollingObserver(timeout=POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Shared debounce base
# ---------------------------------------------------------------------------

class _DebouncedHandler(FileSystemEventHandler):
    """Base handler with 3-second debounce so rapid saves don't spam the indexer."""

    _DEBOUNCE_SECONDS = 3.0

    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, rel_path: str, deleted: bool = False):
        if not rel_path or self._should_ignore(rel_path):
            return
        with self._lock:
            prev = self._timers.pop(rel_path, None)
            if prev:
                prev.cancel()
            t = threading.Timer(self._DEBOUNCE_SECONDS, self._process, args=(rel_path, deleted))
            self._timers[rel_path] = t
            t.start()

    def _process(self, rel_path: str, deleted: bool):
        raise NotImplementedError

    def _should_ignore(self, rel_path: str) -> bool:
        raise NotImplementedError

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

    def _rel_path(self, src_path: str) -> str | None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Obsidian vault handler
# ---------------------------------------------------------------------------

class _ObsidianHandler(_DebouncedHandler):
    """Watches the vault for .md and .pdf changes."""

    @staticmethod
    def _should_ignore(rel_path: str) -> bool:
        parts = Path(rel_path).parts
        filename = parts[-1] if parts else ""

        if any(p.startswith(".") for p in parts):
            return True
        if filename.startswith("~") or filename.endswith("~"):
            return True
        if not (filename.endswith(".md") or filename.endswith(".pdf")):
            return True
        return False

    def _rel_path(self, src_path: str) -> str | None:
        try:
            return str(Path(src_path).relative_to(VAULT_PATH))
        except ValueError:
            return None

    def _process(self, rel_path: str, deleted: bool):
        try:
            if deleted:
                self.indexer.remove_file(rel_path)
                logger.info("Removed from index: %s", rel_path)
            else:
                self.indexer.index_file(rel_path)
        except Exception as e:
            logger.error("Error processing %s: %s", rel_path, e)


# ---------------------------------------------------------------------------
# Paperless archive handler
# ---------------------------------------------------------------------------

class _PaperlessHandler(_DebouncedHandler):
    """Watches the Paperless archive/ directory for PDF changes.

    Uses inotify on Linux so indexing is triggered immediately when Paperless
    writes a new or updated archive PDF – no polling delay.
    """

    @staticmethod
    def _should_ignore(rel_path: str) -> bool:
        filename = Path(rel_path).name
        if filename.startswith(".") or filename.startswith("~"):
            return True
        return not filename.lower().endswith(".pdf")

    def _rel_path(self, src_path: str) -> str | None:
        try:
            return str(Path(src_path).relative_to(PAPERLESS_ARCHIVE_PATH))
        except ValueError:
            return None

    def _process(self, rel_path: str, deleted: bool):
        try:
            if deleted:
                self.indexer.remove_file(rel_path, source="paperless")
                logger.info("Removed paperless doc from index: %s", rel_path)
            else:
                self.indexer.index_file(rel_path, base_path=PAPERLESS_ARCHIVE_PATH, source="paperless")
        except Exception as e:
            logger.error("Error processing paperless %s: %s", rel_path, e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_watcher(indexer: Indexer, watch_obsidian: bool = True, watch_paperless: bool = True):
    """Start file watchers for vault and/or Paperless archive.

    Returns the started observer (call ``.stop()`` to shut down).
    At least one watched path must exist; logs a warning otherwise.
    """
    observer = _make_observer()
    watching_any = False

    if watch_obsidian:
        vault_path = Path(VAULT_PATH)
        if vault_path.exists():
            observer.schedule(_ObsidianHandler(indexer), str(vault_path), recursive=True)
            logger.info("Watching vault for changes: %s", vault_path)
            watching_any = True
        else:
            logger.warning("Vault path does not exist, skipping watcher: %s", vault_path)

    if watch_paperless and PAPERLESS_ARCHIVE_PATH:
        archive_path = Path(PAPERLESS_ARCHIVE_PATH)
        if archive_path.exists():
            observer.schedule(_PaperlessHandler(indexer), str(archive_path), recursive=True)
            logger.info("Watching Paperless archive for changes: %s", archive_path)
            watching_any = True
        else:
            logger.warning("Paperless archive path does not exist, skipping: %s", archive_path)

    if not watching_any:
        logger.warning("No watchable paths found – file watcher inactive.")

    observer.daemon = True
    observer.start()
    return observer

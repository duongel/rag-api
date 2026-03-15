import os

VAULT_PATH = os.environ.get("VAULT_PATH", "/obsidian")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "/app/data/chroma")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8484")
API_BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}

# Which data sources to index: "obsidian" | "paperless" | "all"
DATA_SOURCES = os.environ.get("DATA_SOURCES", "all")

# Paperless-NGX integration (optional).
# Set PAPERLESS_ARCHIVE_PATH to a bind-mounted copy of the Paperless archive/ directory.
# If PAPERLESS_URL + PAPERLESS_TOKEN are also set, document titles and tags are fetched
# from the REST API and stored as metadata alongside the indexed text.
PAPERLESS_ARCHIVE_PATH = os.environ.get("PAPERLESS_ARCHIVE_PATH", "")
PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "")
PAPERLESS_TOKEN = os.environ.get("PAPERLESS_TOKEN", "")
PAPERLESS_PUBLIC_URL = os.environ.get("PAPERLESS_PUBLIC_URL", "")

# Minimum content length (chars) before splitting into chunks.
# Shorter files are indexed as a single chunk.
CHUNK_MIN_LENGTH = 500

# Chunks shorter than this are discarded (too noisy for embeddings).
CHUNK_DISCARD_LENGTH = 5

# Polling interval in seconds for the file watcher (PollingObserver).
# Used as fallback on macOS where inotify is unavailable inside Docker bind mounts.
POLL_INTERVAL = 5

API_PORT = 8080

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
# Set PAPERLESS_URL + PAPERLESS_TOKEN to enable.
# All documents are fetched via the REST API.
PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "")
PAPERLESS_TOKEN = os.environ.get("PAPERLESS_TOKEN", "")
PAPERLESS_PUBLIC_URL = os.environ.get("PAPERLESS_PUBLIC_URL", "")

# Internal URL that Paperless uses to reach rag-api for webhook callbacks.
# Defaults to http://rag-api:8080 (Docker-internal).
RAG_API_INTERNAL_URL = os.environ.get("RAG_API_INTERNAL_URL", "http://rag-api:8080")

# Minimum content length (chars) before splitting into chunks.
# Shorter files are indexed as a single chunk.
CHUNK_MIN_LENGTH = 500

# Chunks shorter than this are discarded (too noisy for embeddings).
CHUNK_DISCARD_LENGTH = 5

# Maximum chunk size (chars). Chunks exceeding this are recursively split
# at the next-best boundary (---, paragraph, newline, hard cut).
# 1500 chars ≈ 200–400 tokens – well within nomic-embed-text's 8192 context
# and in the sweet spot for retrieval quality.
MAX_CHUNK_SIZE = 1500

# Overlap (chars) when a chunk must be hard-split at MAX_CHUNK_SIZE.
# Preserves context across chunk boundaries.
CHUNK_OVERLAP = 200

# Polling interval in seconds for the file watcher (PollingObserver).
# Used as fallback on macOS where inotify is unavailable inside Docker bind mounts.
POLL_INTERVAL = 5

# Set WATCHER_POLLING=true to force PollingObserver even on Linux.
# Needed for Docker Desktop on macOS, where the container reports Linux but
# inotify events are unreliable over the virtio/bind-mount layer.
WATCHER_POLLING = os.environ.get("WATCHER_POLLING", "false").lower() in {"1", "true", "yes", "on"}

API_PORT = 8080

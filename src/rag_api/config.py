import os

VAULT_PATH = os.environ.get("VAULT_PATH", "/obsidian")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "/app/data/chroma")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8484")
API_BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}

# Which data sources to index: "obsidian" | "paperless" | "all"
DATA_SOURCES = os.environ.get("DATA_SOURCES", "all")

# Minimum content length (chars) before splitting into chunks.
# Shorter files are indexed as a single chunk.
CHUNK_MIN_LENGTH = 500

# Chunks shorter than this are discarded (too noisy for embeddings).
CHUNK_DISCARD_LENGTH = 5

# Polling interval in seconds for the file watcher (PollingObserver).
# Required because inotify events are unreliable over Docker bind-mounts on macOS.
POLL_INTERVAL = 5

API_PORT = 8080

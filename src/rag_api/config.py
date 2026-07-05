import os

VAULT_PATH = os.environ.get("VAULT_PATH", "/obsidian")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "/app/data/chroma")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
# Default embedding model. ``bge-m3`` is a strong multilingual model (1024-dim,
# 8k context) that markedly outperforms nomic-embed-text on German content.
# Overriding this to a model with a different vector dimension triggers an
# automatic collection rebuild + full re-index on the next start.
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

# Task-specific embedding prefixes. Some models (nomic-embed-text) require
# ``search_document:`` / ``search_query:`` prefixes; most others (bge-m3,
# mxbai-embed-large) perform best without any prefix. ``auto`` picks the right
# behavior from the model name; set explicit strings to override.
EMBED_DOC_PREFIX = os.environ.get("EMBED_DOC_PREFIX", "auto")
EMBED_QUERY_PREFIX = os.environ.get("EMBED_QUERY_PREFIX", "auto")

# Number of chunks embedded per Ollama request during indexing. Higher values
# improve throughput on capable hardware at the cost of larger requests.
EMBED_BATCH = int(os.environ.get("EMBED_BATCH", "64"))

# ---------------------------------------------------------------------------
# Cross-encoder reranking (optional, opt-in)
# ---------------------------------------------------------------------------
# When enabled, search retrieves a larger candidate pool via vector/keyword
# search and reorders it with a cross-encoder reranker served over HTTP
# (Hugging Face text-embeddings-inference or Infinity, ``POST /rerank``).
# Disabled by default so no external service is required.
RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
RERANK_URL = os.environ.get("RERANK_URL", "")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# Number of candidates fetched and sent to the reranker before truncating to
# the caller's top_k. Larger pools improve recall at the cost of latency.
RERANK_CANDIDATES = int(os.environ.get("RERANK_CANDIDATES", "30"))
RERANK_TIMEOUT_SECONDS = int(os.environ.get("RERANK_TIMEOUT_SECONDS", "15"))
# Each candidate document is truncated to this many characters before being
# sent to the reranker. Cross-encoder latency scales with sequence length, so
# capping it keeps reranking fast on CPU-only rerankers; the leading portion of
# a chunk carries the strongest relevance signal. Set to 0 to disable trimming.
RERANK_DOC_CHARS = int(os.environ.get("RERANK_DOC_CHARS", "512"))

# ---------------------------------------------------------------------------
# HNSW index tuning (ChromaDB)
# ---------------------------------------------------------------------------
# Higher values improve recall/quality at the cost of memory and build time —
# comfortably affordable on modern hardware. Applied when the collection is
# first created; changing them later requires a collection rebuild.
HNSW_M = int(os.environ.get("HNSW_M", "32"))
HNSW_CONSTRUCTION_EF = int(os.environ.get("HNSW_CONSTRUCTION_EF", "200"))
HNSW_SEARCH_EF = int(os.environ.get("HNSW_SEARCH_EF", "128"))

# When the embedding model is missing from Ollama, pull it automatically via
# the Ollama API instead of failing. This makes setups that point at an
# external/shared Ollama work out of the box (the model no longer has to be
# pulled manually beforehand).
EMBED_MODEL_AUTO_PULL = os.environ.get("EMBED_MODEL_AUTO_PULL", "true").lower() in {"1", "true", "yes", "on"}
# Maximum time to wait for a model pull to finish (seconds).
EMBED_MODEL_PULL_TIMEOUT_SECONDS = int(os.environ.get("EMBED_MODEL_PULL_TIMEOUT_SECONDS", "600"))
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
# 1500 chars ≈ 200–400 tokens – well within bge-m3's 8192 context
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

# Number of worker threads for concurrent Paperless document embedding
# during full reindex. Higher values speed up initial indexing but increase
# Ollama load. Set to 1 to disable concurrency.
PAPERLESS_REINDEX_WORKERS = int(os.environ.get("PAPERLESS_REINDEX_WORKERS", "8"))

# Worker threads for parallel Paperless page prefetching during reindex.
# Raised default suits multi-core hardware.
PAPERLESS_PREFETCH_WORKERS = int(os.environ.get("PAPERLESS_PREFETCH_WORKERS", "8"))

# Number of worker threads for concurrent Obsidian/PDF embedding during a full
# vault reindex. Each worker embeds a file in parallel; DB writes are still
# serialized. Effective throughput also depends on how many parallel requests
# Ollama serves (see OLLAMA_NUM_PARALLEL). Set to 1 to disable concurrency.
OBSIDIAN_REINDEX_WORKERS = int(os.environ.get("OBSIDIAN_REINDEX_WORKERS", "8"))

API_PORT = 8080

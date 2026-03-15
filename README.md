# RAG API

Self-hosted RAG system for an Obsidian vault and Paperless-NGX. Runs entirely in Docker.

## Architecture

```
┌────────────────────┐     ┌──────────────────────┐
│   rag-api          │────▶│   ollama             │
│   (Python/FastAPI) │     │   (nomic-embed-text) │
│   + ChromaDB       │     │   Apple Silicon GPU  │
│   + File Watcher   │     └──────────────────────┘
│                    │◀── /vault (read-only mount)
└────────────────────┘
        │
   rag-network (or any external Docker network)
```

All services run inside a Docker network. Host port publishing is optional.
All data-bearing endpoints require a bearer token by default.

## Requirements

- macOS with Apple Silicon
- Docker environment ([Colima](https://github.com/abiosoft/colima) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)) running

## Setup

```bash
git clone git@github.com:duongel/rag-api.git
cd rag-api
chmod +x start.sh
./start.sh
```

The script asks:

1. **Path to vault** – directory containing the `.md` files
2. **External Ollama?** – if Ollama is already running elsewhere, provide its URL
3. **Publish API on the host?** – `No` keeps rag-api reachable only inside Docker; `Yes` exposes it on `127.0.0.1:8484`
4. **Require bearer token?** – prompted for both modes; see access modes below
5. **External Docker network?** – name of an existing network to join (e.g. `npm-net`); leave empty to use the default `rag-network`

Then:
- Ollama starts (first run: pulls `nomic-embed-text`, ~1 min)
- `rag-api` starts and indexing begins in the background
- macOS notification + terminal output when ready

## Access Modes

| Mode | Host port | Auth | `.env` |
|---|---|---|---|
| Internal, no auth | ✗ | ✗ | `ACCESS_MODE=internal` `AUTH_REQUIRED=false` |
| Internal, token | ✗ | ✓ | `ACCESS_MODE=internal` `AUTH_REQUIRED=true` |
| Host, token | ✓ | ✓ | `ACCESS_MODE=host` `AUTH_REQUIRED=true` |
| Host, no auth | ✓ | ✗ | `ACCESS_MODE=host` `AUTH_REQUIRED=false` ⚠️ testing only |

Set the token once in your shell when auth is enabled:

```bash
export API_BEARER_TOKEN='<your-token>'
```

## n8n Integration (same Docker host)

If n8n runs on the same machine, connect rag-api to its network during setup (e.g. `npm-net`) and choose internal mode without auth:

```env
ACCESS_MODE=internal
AUTH_REQUIRED=false
DOCKER_NETWORK=npm-net
```

n8n then reaches rag-api directly – no exposed port, no token required:

```
http://rag-api:8080/search
http://rag-api:8080/keyword-search
http://rag-api:8080/note?path=...
```

To keep auth even on the internal network, set `AUTH_REQUIRED=true` and pass the bearer token from n8n.

## Testing

```bash
# Health check (no auth required)
curl -s http://localhost:8484/health

# Indexing status
curl -s http://localhost:8484/status \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Semantic search
curl -s http://localhost:8484/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "heat pump noises", "top_k": 3}'

# Keyword search
curl -s http://localhost:8484/keyword-search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "ProductCard"}'
```

## Useful Commands

```bash
# Logs
docker logs -f rag-api

# Manual reindex
curl -s -X POST http://localhost:8484/reindex \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Statistics
curl -s http://localhost:8484/stats \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Stop
docker compose down

# Stop and delete all data
docker compose down -v
```

## Agent Skill

[`SKILL.md`](./SKILL.md) documents all endpoints with curl examples.
It can be passed as context to any agent (OpenAI, Anthropic, Copilot, …).
It also includes lean OpenAI/Anthropic-compatible tool definitions and a compatibility matrix – no MCP required.

## Notes

- **GPU**: Ollama uses the Metal GPU on Apple Silicon.
- **File Watcher**: Uses `PollingObserver` (every 5 sec) because inotify events are unreliable over Docker bind-mounts on macOS.

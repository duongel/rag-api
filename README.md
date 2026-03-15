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
   rag-network
```

All services run inside the Docker network `rag-network` by default. Host port publishing is optional and enabled only through `docker-compose.host.yml`.

All data-bearing endpoints require a bearer token by default. Only `/health`, `/docs`, `/openapi.json`, and `/skill` are intended to be reachable without authentication. For trusted same-network containers, you can explicitly choose internal-only mode and disable auth during setup.

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running

## Setup

```bash
git clone <repo-url>
cd rag-api
chmod +x start.sh
./start.sh
```

The script asks:
1. **Path to vault** – directory containing the `.md` files
2. **External Ollama?** – if Ollama is already running, its URL can be provided
3. **Publish API on the host?** – choose `No` to keep `rag-api` reachable only inside Docker
4. **Require bearer token in internal-only mode?** – optional when only trusted containers share the network

Then:
- Ollama container starts (first run: pulls `nomic-embed-text`, ~1 min)
- `rag-api` starts either on the internal Docker network only or on `http://127.0.0.1:8484`
- Indexing runs in the background – macOS notification + terminal output when done
- A random API bearer token is generated and stored in `.env` whenever auth is enabled

Set the token once in your shell before calling protected endpoints:

```bash
export API_BEARER_TOKEN='<your-token>'
```

## Testing

```bash
# Health check
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

## Internal-only Mode for n8n

If `n8n` runs on the same machine in Docker, choose internal-only mode during setup or set this in `.env`:

```bash
ACCESS_MODE=internal
AUTH_REQUIRED=false
DOCKER_NETWORK=rag-network
```

Then start `n8n` on the same Docker network and call:

```text
http://rag-api:8080
```

If you want internal-only mode but still keep authentication, set `AUTH_REQUIRED=true` and send the same bearer token from `n8n`.

## Agent Skill

[`SKILL.md`](./SKILL.md) documents all endpoints with authenticated curl examples.
It can be passed as context to any agent (OpenAI, Anthropic, Copilot, …).
It also includes lean OpenAI/Anthropic-compatible tool definitions and a compatibility matrix – no MCP required.

## Notes

- **GPU**: Ollama uses the Metal GPU on Apple Silicon.
- **File Watcher**: Uses `PollingObserver` (every 5 sec) because inotify events are unreliable over Docker bind-mounts on macOS.

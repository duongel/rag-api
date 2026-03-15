# RAG API

[![Release](https://img.shields.io/github/v/release/duongel/rag-api)](https://github.com/duongel/rag-api/releases)
[![Docker Image](https://img.shields.io/github/v/release/duongel/rag-api?label=ghcr.io&logo=docker)](https://github.com/duongel/rag-api/pkgs/container/rag-api)

> **TL;DR** — One command indexes your Obsidian vault and Paperless-NGX documents and exposes `/search` and `/keyword-search` endpoints that any LLM agent, n8n workflow, or custom client can query. Runs entirely inside Docker alongside your existing services — no cloud, no subscriptions. [`SKILL.md`](./SKILL.md) ships ready-to-use tool definitions for OpenAI- and Anthropic-compatible agents.

Self-hosted RAG system for an Obsidian vault and Paperless-NGX. Runs entirely in Docker.

## Architecture

```
┌────────────────────┐     ┌──────────────────────┐
│   rag-api          │────▶│   ollama             │
│   (Python/FastAPI) │     │   (nomic-embed-text) │
│   + ChromaDB       │     │   GPU (optional)     │
│   + File Watcher   │     └──────────────────────┘
│                    │◄── /vault (read-only mount)
└────────────────────┘
        │
   rag-network (or any external Docker network)
```

All services run inside a Docker network. Host port publishing is optional.  
All data-bearing endpoints require a bearer token by default.

## Agent / LLM Integration

[`SKILL.md`](./SKILL.md) documents every endpoint with curl examples, ready-to-use tool definitions (OpenAI- and Anthropic-compatible), and a compatibility matrix. Pass it as context to any LLM agent — no MCP required.

## Requirements

- Linux (x86_64 or arm64) or macOS
- Docker Engine (or Docker Desktop on macOS) running
- `curl` (for the one-liner bootstrap)
- `git`

## Installation

### One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
```

Clones the repo to `~/rag-api` and runs the interactive setup. Safe to re-run — updates an existing installation.

### Manual (advanced / development)

```bash
git clone git@github.com:duongel/rag-api.git
cd rag-api
chmod +x start.sh
./start.sh
```

The setup script asks:

1. **Path to vault** – directory containing the `.md` files
2. **External Ollama?** – if Ollama is already running elsewhere, provide its Docker service/container name on the shared network (and optionally override the URL)
3. **Publish API on the host?** – `No` keeps rag-api reachable only inside Docker; `Yes` exposes it on `127.0.0.1:8484`
4. **Require bearer token?** – prompted for both modes; see access modes below
5. **External Docker network?** – name of an existing network to join (e.g. `npm-net`); leave empty to use the default `rag-network`

Then:
- Ollama starts (first run: pulls `nomic-embed-text`, ~1 min) unless you use an existing external Ollama
- `rag-api` starts and indexing begins in the background
- macOS notification + terminal output when ready

> **Re-run behaviour:** `DATA_SOURCES` is persisted in `.env`. Re-running without a flag keeps the stored value — so a previous `--obsidian-only` run silently stays obsidian-only on the next bare `./start.sh`. To switch, either pass the flag explicitly (e.g. `./start.sh --paperless-only`) or answer **n** to the "Use this configuration?" prompt, which re-runs the full setup wizard with the CLI-provided value (no flag = `all`).

### Docker image

Pre-built multi-arch images (`linux/amd64`, `linux/arm64`) are published automatically on every release:

```bash
docker pull ghcr.io/duongel/rag-api:latest
```

Available tags: `latest`, `1.0.0`, `1.0`, …

> **Note:** After the first automated release, the package must be set to **public** once:  
> GitHub → Packages → `rag-api` → Package settings → Change visibility → Public

## Updates

```bash
# Re-run the installer – pulls latest code and restarts
curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash

# Or manually
cd ~/rag-api && git pull && ./start.sh
```

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

If you run in internal mode on a shared Docker network such as `npm-net`, test from another container on that network:

```bash
# Health check (no auth required)
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s http://rag-api:8080/health

# Indexing status
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s http://rag-api:8080/status \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Semantic search
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s http://rag-api:8080/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "heat pump noises", "top_k": 3}'

# Keyword search
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s http://rag-api:8080/keyword-search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "ProductCard"}'
```

## Useful Commands

```bash
# Logs
docker compose logs -f rag-api

# Manual reindex
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s -X POST http://rag-api:8080/reindex \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Statistics
docker run --rm --network npm-net curlimages/curl:8.7.1 \
  -s http://rag-api:8080/stats \
  -H "Authorization: Bearer $API_BEARER_TOKEN"

# Stop
docker compose down

# Stop and delete all data
docker compose down -v
```

## Notes

- **Image**: Pre-built and published to `ghcr.io/duongel/rag-api` on every release. No local build required.
- **GPU**: Ollama uses the Metal GPU on Apple Silicon; on Linux it uses CUDA or CPU depending on your Ollama setup.
- **File Watcher**: Uses `InotifyObserver` on Linux (real kernel events, zero overhead). Falls back to `PollingObserver` on macOS.

<div align="center">

<img src=".github/logo.svg" alt="RAG API" width="120">

# RAG API

**Self-hosted RAG for Obsidian & Paperless-NGX**

[![Release](https://img.shields.io/github/v/release/duongel/rag-api?style=flat-square&color=blue)](https://github.com/duongel/rag-api/releases)
[![Docker](https://img.shields.io/github/v/release/duongel/rag-api?label=ghcr.io&logo=docker&style=flat-square&color=blue)](https://github.com/duongel/rag-api/pkgs/container/rag-api)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)

Makes Obsidian notes and Paperless-NGX documents searchable for any LLM agent
via a ready-to-use [skill](./SKILL.md). Runs entirely in Docker.

</div>

---

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
```
The interactive setup asks for your vault path, Paperless API credentials, Ollama location, and access mode. 

> [!TIP]
> Safe to re-run to update.

### To install with only one data source:

#### Obsidian only
```bash
curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash -s -- --obsidian-only
````

#### Paperless-ngx only
```bash
curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash -s -- --paperless-only
```



<details>
<summary>Manual install (development)</summary>

```bash
git clone git@github.com:duongel/rag-api.git
cd rag-api && ./start.sh
```

</details>

<details>
<summary>Docker image</summary>

Pre-built multi-arch images (`linux/amd64`, `linux/arm64`) are published on every release:

```bash
docker pull ghcr.io/duongel/rag-api:latest
```

</details>

## Agent Integration

[`SKILL.md`](./SKILL.md) contains endpoint documentation, curl examples, and copy-paste tool definitions for all major providers. Serve it as context to any LLM agent — no MCP server required.

Recent search additions:

- `POST /hybrid-search` combines semantic and keyword retrieval for mixed natural-language + exact-term queries
- `sort_by_date: true` supports "latest / newest" document queries
- `paperless_document_type` adds structured Paperless filtering by document type
- For Paperless questions, agents should first set the strongest available `paperless_*` filters and only then run semantic, hybrid, or keyword search on that filtered subset

| Provider | Format | Where to use |
|---|---|---|
| **OpenAI** | `functions` / `tools` array | ChatGPT, GPT-4o, Assistants API, Azure OpenAI |
| **Anthropic** | `tools` with `input_schema` | Claude, Claude Code, Amazon Bedrock |
| **Google** | `function_declarations` | Gemini, Vertex AI |
| **Compatible** | OpenAI format | Mistral, Groq, Ollama, Together AI, DeepSeek, Fireworks, Perplexity |

**How it works:** Copy the tool definition for your provider from [`SKILL.md`](./SKILL.md) into your agent's tool/function list. The agent calls rag-api over HTTP to search your vault and Paperless documents. Works with any framework that supports HTTP tool calls (LangChain, CrewAI, n8n, custom agents).

**Simplest approach:** Pass the full [`SKILL.md`](./SKILL.md) as system context — the agent discovers the endpoints and calls them directly.

Typical endpoint choices:

- Use `/search` for concepts, explanations, and broad semantic questions
- Use `/keyword-search` for abbreviations, identifiers, filenames, and exact strings
- Use `/hybrid-search` for queries like "Kaufvertrag Grundstück Montabaur" or "letzte Telekom Rechnung"
- Use `/documents` for filter-only Paperless lookups by tags, correspondent, year, or document type
- For Paperless queries, prefer `paperless_tags`, `paperless_correspondent`, `paperless_created_year`, and `paperless_document_type` before ranking

## Architecture

```mermaid
graph LR
    AGENT["LLM Agent<br><sub>uses SKILL.md / tools</sub>"]:::ext

    subgraph Docker Network
        API["rag-api<br><sub>FastAPI · ChromaDB</sub>"]
        SEARCH["/search · /keyword-search · /hybrid-search · /documents"]
        FILTER["Paperless pre-filter<br><sub>tags / correspondent / year / document type</sub>"]
        CHROMA["ChromaDB index<br><sub>semantic + keyword retrieval</sub>"]
        OLL["ollama<br><sub>bge-m3</sub>"]
        RERANK["reranker (optional)<br><sub>bge-reranker-v2-m3</sub>"]:::ext
    end

    VAULT["Obsidian Vault"]:::ext
    PAPER["Paperless-NGX"]:::ext

    AGENT -->|HTTP API| API
    API --> SEARCH
    SEARCH --> FILTER
    FILTER <-->|REST API| PAPER
    SEARCH --> CHROMA
    CHROMA -->|embeddings| OLL
    SEARCH -.->|top candidates| RERANK
    VAULT -->|read-only mount| CHROMA
    PAPER -->|content + metadata| CHROMA
    PAPER -->|webhook| API

    classDef ext fill:#f0f0f0,stroke:#999,stroke-width:1px,color:#333
```

- Obsidian files are watched via inotify and indexed on change
- Paperless documents are fetched via REST API; a webhook is auto-registered for real-time updates
- Paperless queries can be pre-filtered by tag, correspondent, year, and document type before semantic or hybrid ranking
- `/hybrid-search` combines semantic and keyword retrieval, while `sort_by_date` supports newest-first document queries
- All data-bearing endpoints require a bearer token by default

## Retrieval Quality

The index is tuned for retrieval accuracy on modern multi-core hardware:

- **Embedding model** — defaults to `bge-m3` (1024-dim, strong multilingual
  retrieval incl. German). Override with `EMBED_MODEL`. Task prefixes are
  auto-selected per model (`nomic-*` needs them, `bge-m3` does not).
- **Cross-encoder reranker (optional)** — reorders the top candidates for a
  large precision gain. Disabled by default. The installer (`install.sh` /
  `start.sh`) prompts to enable it and starts the container automatically. To
  enable it manually instead:

  ```bash
  docker compose --profile reranker up -d   # start the reranker service
  # then set on rag-api:
  RERANK_ENABLED=true
  ```

  Search stays fully functional if the reranker is off or unreachable.
- **HNSW tuning** — `HNSW_M`, `HNSW_CONSTRUCTION_EF`, `HNSW_SEARCH_EF` trade
  memory/build time for recall. Defaults (32 / 200 / 128) suit 16 GB+ RAM.

> [!IMPORTANT]
> Changing `EMBED_MODEL` (or `HNSW_M` / `HNSW_CONSTRUCTION_EF`) requires a full
> re-index. The collection stores its embedding model and is rebuilt
> automatically on the next startup when the model changes.

## Indexing Performance

Full reindexing is parallelized to make use of multi-core hardware. Both the
Obsidian/PDF and Paperless reindex paths embed files concurrently while
database writes stay serialized:

- **Worker counts** — `OBSIDIAN_REINDEX_WORKERS`, `PAPERLESS_REINDEX_WORKERS`,
  `PAPERLESS_PREFETCH_WORKERS` (default `8` each). Raise them on strong CPUs;
  set to `1` to disable concurrency.
- **Embedding batch** — `EMBED_BATCH` (default `64`) chunks per Ollama request.
- **Ollama concurrency** — worker threads only help if Ollama serves requests
  in parallel. For the bundled local Ollama container set
  `OLLAMA_NUM_PARALLEL` (default `4`) to roughly match the worker count, and
  `OLLAMA_KEEP_ALIVE` (default `30m`) to keep the model resident.

> [!TIP]
> On a machine like a Ryzen AI 9 HX 370 (12c/24t, 64 GB) try
> `OBSIDIAN_REINDEX_WORKERS=12`, `PAPERLESS_REINDEX_WORKERS=12` and
> `OLLAMA_NUM_PARALLEL=8`. The sweet spot is CPU- and model-dependent —
> increase gradually and watch Ollama load.

## Access Modes

| Mode | Use case | Reachable at | Bind | Auth |
|---|---|---|---|:---:|
| **Internal** | Other containers on the same Docker network (e.g. n8n) | `http://rag-api:8080` | no port published | optional |
| **Host** | Apps on this machine only | `http://localhost:8484` | `127.0.0.1:8484` | recommended |
| **Network** | Other machines / external Paperless | `http://<your-ip>:8484` | `0.0.0.0:8484` | enforced |

> [!NOTE]
> **Network** mode binds to all interfaces and enforces authentication.
> When combined with Paperless, setup asks for the webhook callback URL so Paperless can reach rag-api.

## n8n Integration

Connect rag-api to n8n's Docker network (e.g. `npm-net`) with `ACCESS_MODE=internal`. n8n reaches the API directly at `http://rag-api:8080` — no exposed port, no token needed.

## Quick Reference

```bash
docker compose logs -f rag-api          # Logs
curl -X POST .../reindex                # Manual reindex
curl .../stats                          # Statistics
docker compose down                     # Stop
docker compose down -v                  # Stop + delete data
```

## Notes

| Topic | Detail |
|---|---|
| **GPU** | Metal on Apple Silicon; CUDA or CPU on Linux |
| **File Watcher** | inotify on Linux, polling on macOS (Obsidian only — Paperless uses webhooks) |
| **Paperless Webhook** | Auto-registered on startup; documents are re-indexed in real-time |
| **Data Sources** | `--obsidian-only` / `--paperless-only` to limit; default indexes both |
| **Updates** | Re-run the install command or `git pull && ./start.sh` |

## License

[MIT](LICENSE)

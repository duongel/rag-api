# RAG API – Agent Skill

## Description

This tool searches a self-hosted knowledge base (Obsidian vault and Paperless-NGX) using semantic and keyword search.
It is intended for trusted clients that authenticate with a bearer token.

## Base URL

```
http://localhost:8484
```

Internal-only Docker deployments can use:

```text
http://rag-api:8080
```

**Agent integration:**
| Format | URL |
|---|---|
| This document (Markdown) | `http://localhost:8484/skill` |
| OpenAPI 3.x spec (GPT Actions, LangChain, …) | `http://localhost:8484/openapi.json` |
| Swagger UI | `http://localhost:8484/docs` |

## Authentication

All data-bearing endpoints require this header:

```http
Authorization: Bearer <API_BEARER_TOKEN>
```

Recommended shell setup:

```bash
export API_BEARER_TOKEN='<your-token>'
```

For trusted internal-only deployments, authentication can be disabled with `AUTH_REQUIRED=false`. In that mode, omit the `Authorization` header.

## Tool Definitions for Agents

Goal: no MCP, no extra services, minimal context. Agents should prefer calling the HTTP API directly and include the bearer token on every protected request.

### Minimal Tool Set

For most agents, these three operations are sufficient:

1. `search_notes`
2. `keyword_search_notes`
3. `get_note`

`reindex` is optional and mainly useful for admin/maintenance tasks.

### OpenAI-compatible Tool Definition

This format is suitable for agents that use JSON tool definitions or function calling.
Also used by: **Mistral**, **Groq**, **Together AI**, **Ollama**, **Azure OpenAI**, **Fireworks AI**, **Perplexity**, **DeepSeek**, and most OpenAI-compatible providers.

```json
[
  {
    "type": "function",
    "function": {
      "name": "search_notes",
      "description": "Semantic search in an Obsidian vault. Use for concepts, explanations, broad topics, and questions where wording may differ from the notes.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results.", "default": 5 },
          "expand_links": { "type": "boolean", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags.", "default": true },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." }
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "keyword_search_notes",
      "description": "Exact text search in filenames and note content. Use for abbreviations, URLs, class names, enum values, identifiers, and exact strings.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Exact search string." },
          "top_k": { "type": "integer", "description": "Maximum number of results.", "default": 5 }
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_note",
      "description": "Return the full Markdown content of a note by relative path.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": { "type": "string", "description": "Relative note path, e.g. Projects/Home/Heating.md" }
        },
        "required": ["path"]
      }
    }
  }
]
```

Recommended HTTP mapping:

| Tool | HTTP |
|---|---|
| `search_notes` | `POST /search` |
| `keyword_search_notes` | `POST /keyword-search` |
| `get_note` | `GET /note?path=...` |

Every mapping above also requires `Authorization: Bearer <API_BEARER_TOKEN>`.

### Anthropic-compatible Tool Definition

This format is for Claude/Anthropic setups that expect tools with `name`, `description`, and `input_schema`.

```json
[
  {
    "name": "search_notes",
    "description": "Semantic search in the Obsidian vault. Best for concepts, explanations, broad topics, and fuzzy user questions.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "top_k": { "type": "integer", "default": 5 },
        "expand_links": { "type": "boolean", "default": true },
        "min_score": { "type": "number", "default": 0.0 }
      },
      "required": ["query"]
    }
  },
  {
    "name": "keyword_search_notes",
    "description": "Exact keyword search in filenames and content. Best for abbreviations, URLs, identifiers, class names, and enum values.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "top_k": { "type": "integer", "default": 5 }
      },
      "required": ["query"]
    }
  },
  {
    "name": "get_note",
    "description": "Fetch the full Markdown content of one note by relative path.",
    "input_schema": {
      "type": "object",
      "properties": {
        "path": { "type": "string" }
      },
      "required": ["path"]
    }
  }
]
```

### Gemini-compatible Tool Definition

This format is for Google Gemini setups using `function_declarations`.

```json
{
  "function_declarations": [
    {
      "name": "search_notes",
      "description": "Semantic search in the Obsidian vault. Best for concepts, explanations, broad topics, and fuzzy user questions.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results." },
          "expand_links": { "type": "boolean", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags." },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." }
        },
        "required": ["query"]
      }
    },
    {
      "name": "keyword_search_notes",
      "description": "Exact keyword search in filenames and content. Best for abbreviations, URLs, identifiers, class names, and enum values.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Exact search string." },
          "top_k": { "type": "integer", "description": "Maximum number of results." }
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_note",
      "description": "Fetch the full Markdown content of one note by relative path.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": { "type": "string", "description": "Relative note path, e.g. Projects/Home/Heating.md" }
        },
        "required": ["path"]
      }
    }
  ]
}
```

### Cohere-compatible Tool Definition

This format is for Cohere Command R/R+ setups using `parameter_definitions`.

```json
[
  {
    "name": "search_notes",
    "description": "Semantic search in the Obsidian vault. Best for concepts, explanations, broad topics, and fuzzy user questions.",
    "parameter_definitions": {
      "query": { "type": "str", "description": "Natural-language search query.", "required": true },
      "top_k": { "type": "int", "description": "Maximum number of results.", "required": false },
      "expand_links": { "type": "bool", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags.", "required": false },
      "min_score": { "type": "float", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions.", "required": false }
    }
  },
  {
    "name": "keyword_search_notes",
    "description": "Exact keyword search in filenames and content. Best for abbreviations, URLs, identifiers, class names, and enum values.",
    "parameter_definitions": {
      "query": { "type": "str", "description": "Exact search string.", "required": true },
      "top_k": { "type": "int", "description": "Maximum number of results.", "required": false }
    }
  },
  {
    "name": "get_note",
    "description": "Fetch the full Markdown content of one note by relative path.",
    "parameter_definitions": {
      "path": { "type": "str", "description": "Relative note path, e.g. Projects/Home/Heating.md", "required": true }
    }
  }
]
```

### Recommended Agent Behavior

- Use `keyword_search_notes` first for abbreviations, URLs, hostnames, model numbers, code symbols, and exact identifiers.
- Use `search_notes` for meanings, concepts, explanations, and topic-based questions.
- For relevant results, fetch the full context with `get_note`.
- Use `min_score: 0.70` as the default for precise questions.
- If `search_notes` unexpectedly returns empty: almost always an identifier issue → try `keyword_search_notes`.

### When Semantic Search Fails (→ Use Keyword)

Semantic search understands meaning, but not exact spelling. It reliably fails for:

| Pattern | Examples |
|---|---|
| Short abbreviations / acronyms | `VPN`, `NVR`, `SSD`, `API`, `NAS`, `PoE` |
| Version numbers / date IDs | `v3.2.1`, `2024-03-15`, `3.0.9` |
| Hostnames / container names | `homeassistant`, `paperless-webserver`, `pihole` |
| IP addresses / ports | `192.168.1.1`, `8080`, `11434` |
| Model / product names | `USG-3P`, `NanoHD`, `EVO Plus` |
| Configuration keys | `VAULT_PATH`, `EMBED_MODEL`, `hnsw:space` |
| Filenames / path segments | `docker-compose.yml`, `ansible/roles/` |

## Compatibility Matrix

This matrix evaluates what works with minimal setup.

| Agent / Tool Type | `SKILL.md` as context | OpenAPI directly | `localhost` directly usable | Out of the box |
|---|---|---|---|---|
| Local coding agent with shell/HTTP | Yes | Yes | Yes | Yes |
| Desktop agent with local tools | Yes | Partial | Yes | Usually yes |
| Agent with JSON tool definitions | Partial | Partial | Only if local | No |
| Agent with OpenAPI import and local runtime | Optional | Yes | Yes | Yes |
| Cloud agent with OpenAPI import | Optional | Yes | No | No |
| Pure chat agent without tool/HTTP access | Yes | No | No | No |

### Practical Notes

- `SKILL.md` is sufficient if the agent can make local HTTP requests or map them through built-in tools.
- `OpenAPI` is the simplest integration path without MCP, if the agent can import external APIs.
- `localhost` is only directly usable if the agent runs on your machine or in the same local runtime.
- For cloud agents, replace `http://localhost:8484` with a reachable `https` URL.
- Without HTTP/tool access, `SKILL.md` is only a behavioral guide, not a real connection to the API.

## Available Endpoints

### 1. Semantic Search

Searches for semantically similar note sections. Also returns linked and tag-connected notes (`expand_links: true`).

Use `min_score` to filter out irrelevant results (recommended: `0.72` for precise questions, `0.65` for broad topics).

```bash
curl -s http://localhost:8484/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the heat pump work?", "top_k": 5, "min_score": 0.70}'
```

**Response:**
```json
{
  "results": [
    {
      "file_path": "Home/Heating/Heatpump.md",
      "section": "How it works",
      "content": "The heat pump extracts energy from outdoor air ...",
      "score": 0.8723,
      "match_type": "semantic"
    },
    {
      "file_path": "Home/Heating/Installation.md",
      "section": "Installation",
      "content": "...",
      "score": 0.7821,
      "match_type": "link_1"
    }
  ],
  "count": 2
}
```

**`match_type` values:**
| Value | Meaning |
|---|---|
| `semantic` | Direct semantic match |
| `link_1` | Directly linked note (wikilink) |
| `backlink` | Another note links to this result |
| `tag` | Same tag, not directly linked |
| `link_2` | Link of a link |

**Score note:** Results with `score < 0.70` are usually not relevant (no real match). If `count: 0` → try keyword search.

### 2. Keyword Search

Case-insensitive full-text search in filenames **and** note content. **Required for:** abbreviations, IDs, version numbers, hostnames, model names, configuration keys – anything that semantic search cannot find by exact spelling.

```bash
curl -s http://localhost:8484/keyword-search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "NanoHD", "top_k": 5}'
```

**Response:**
```json
{
  "results": [
    {
      "file_path": "Network/WiFi/AccessPoints.md",
      "section": "Hardware",
      "content": "4x Unifi NanoHD, PoE, 2.4/5 GHz ...",
      "score": 0.9,
      "match_type": "content"
    }
  ],
  "count": 1
}
```

**More typical keyword queries:**
```bash
# Hostname / container name
'{"query": "homeassistant"}'
# IP address
'{"query": "192.168.1.1"}'
# Configuration key
'{"query": "EMBED_MODEL"}'
# Model / device name
'{"query": "RLN16-410"}'
# Version number
'{"query": "v3.2.1"}'
```

### 3. Retrieve a Note

Returns the full Markdown content of a single note.

```bash
curl -s "http://localhost:8484/note?path=Home/Heating/Heatpump.md" \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

### 4. Trigger Reindex

```bash
curl -s -X POST http://localhost:8484/reindex \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

### 5. Indexing Status

```bash
curl -s http://localhost:8484/status \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
# → {"indexing": false, "indexed_files": 95}
```

### 6. Statistics

```bash
curl -s http://localhost:8484/stats \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
# → {"total_chunks": 187, "total_files": 95, "link_graph_edges": 42}
```

### 7. Health Check

```bash
curl -s http://localhost:8484/health
```

## Search Strategy for Agents

### Which Search to Use?

| Question type | Method | Example |
|---|---|---|
| Concept, meaning, explanation | `/search` | "How does X work?" |
| Short abbreviation / acronym | `/keyword-search` | `"NVR"`, `"VPN"`, `"PoE"` |
| Hostname / container name | `/keyword-search` | `"homeassistant"`, `"pihole"` |
| IP address / port | `/keyword-search` | `"192.168.1.1"`, `"8080"` |
| Model / product name | `/keyword-search` | `"USG-3P"`, `"EVO Plus"` |
| Version number / date ID | `/keyword-search` | `"v3.2.1"`, `"2024-03-15"` |
| Configuration key | `/keyword-search` | `"VAULT_PATH"`, `"hnsw:space"` |
| Class names, enum values | `/keyword-search` | `"SensorType"`, `"ContentType"` |
| Broad topic with context | `/search` with `top_k: 10` | "Everything about network segmentation" |
| Specific file known | `/note` | direct path |

### Recommended Order for Ambiguous Questions

1. Does the question contain an identifier (abbreviation, hostname, model name, ID, version number)? → use `/keyword-search` immediately
2. Otherwise use `/search` with `min_score: 0.70`
3. For relevant results → fetch full context with `/note`
4. If empty → `/search` with `min_score: 0.60` and `top_k: 10`
5. If still empty → `/keyword-search` (semantic may have missed the identifier)

### Multi-step Strategy (Examples)

Question: *"What is the model of my NVR and how many cameras are connected?"*
```
1. keyword-search("NVR")   → finds note with model name and configuration
2. get_note(<file_path>)   → loads full context for a precise answer
```

Question: *"What VLAN strategy do I use for IoT devices?"*
```
1. search("IoT VLAN segmentation", min_score=0.70)  → finds conceptual notes
2. expand_links=true                                 → automatically pulls in linked firewall/switch notes
```

Question: *"Which Docker network does homeassistant use?"*
```
1. keyword-search("homeassistant")   → exact match, even if the note has no prose
```

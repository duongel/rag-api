# RAG API – Agent Skill

## Description

This tool searches a self-hosted knowledge base (Obsidian vault and Paperless-NGX) using semantic and keyword search.
It is intended for trusted clients that authenticate with a bearer token.

## Base URL

```
http://127.0.0.1:8484
```

Internal-only Docker deployments can use:

```text
http://rag-api:8080
```

**Agent integration:**
| Format | URL |
|---|---|
| This document (Markdown) | `http://127.0.0.1:8484/skill` |
| OpenAPI 3.x spec (GPT Actions, LangChain, …) | `http://127.0.0.1:8484/openapi.json` |
| Swagger UI | `http://127.0.0.1:8484/docs` |

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

For most agents, these operations are sufficient:

1. `search_notes`
2. `hybrid_search_notes`
3. `keyword_search_notes`
4. `get_note`
5. `get_filters` — list available Paperless tags, document types, and correspondents

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
      "description": "Semantic search in an Obsidian vault and Paperless-NGX. Use for concepts, explanations, broad topics, and questions where wording may differ from the notes. For Paperless-related queries, first set the strongest available Paperless filters, then search only within that filtered result set. Supports optional newest-first sorting.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results.", "default": 5 },
          "expand_links": { "type": "boolean", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags.", "default": true },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." },
          "sort_by_date": { "type": "boolean", "description": "Sort newest-first by creation date instead of by score. Useful for queries like 'latest invoice'.", "default": false },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive). Example: [\"etron\", \"rechnung\"]" },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year. Example: 2025" },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "hybrid_search_notes",
      "description": "Hybrid search that combines semantic and keyword search, then merges and reranks the results. Best default for natural-language queries that also contain specific identifiers like company names, product names, document types, or invoice terms. For Paperless-related queries, first set the strongest available Paperless filters, then run hybrid search within that filtered result set.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results.", "default": 5 },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." },
          "sort_by_date": { "type": "boolean", "description": "Sort newest-first by creation date instead of by score. Useful for queries like 'latest invoice'.", "default": false },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive)." },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year." },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "keyword_search_notes",
      "description": "Exact text search in filenames and note content. Multi-word queries use AND logic. Use for abbreviations, URLs, class names, enum values, identifiers, and exact strings. For Paperless-related queries, first set the strongest available Paperless filters, then run keyword search within that filtered result set.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Exact search string." },
          "top_k": { "type": "integer", "description": "Maximum number of results.", "default": 5 },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive)." },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year." },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
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
| `hybrid_search_notes` | `POST /hybrid-search` |
| `keyword_search_notes` | `POST /keyword-search` |
| `get_note` | `GET /note?path=...` or `POST /note` |
| `get_filters` | `GET /filters` |

Every mapping above also requires `Authorization: Bearer <API_BEARER_TOKEN>`.

### Anthropic-compatible Tool Definition

This format is for Claude/Anthropic setups that expect tools with `name`, `description`, and `input_schema`.

```json
[
  {
    "name": "search_notes",
    "description": "Semantic search in the Obsidian vault and Paperless-NGX. Best for concepts, explanations, broad topics, and fuzzy user questions. Supports Paperless metadata filters and optional newest-first sorting.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "top_k": { "type": "integer", "default": 5 },
        "expand_links": { "type": "boolean", "default": true },
        "min_score": { "type": "number", "default": 0.0 },
        "sort_by_date": { "type": "boolean", "default": false },
        "paperless_tags": { "type": "array", "items": { "type": "string" } },
        "paperless_correspondent": { "type": "string" },
        "paperless_created_year": { "type": "integer" },
        "paperless_document_type": { "type": "string" }
      },
      "required": ["query"]
    }
  },
  {
    "name": "hybrid_search_notes",
    "description": "Hybrid search that combines semantic and keyword search, then merges and reranks results. Best default for natural-language queries that also contain specific identifiers or Paperless document language.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "top_k": { "type": "integer", "default": 5 },
        "min_score": { "type": "number", "default": 0.0 },
        "sort_by_date": { "type": "boolean", "default": false },
        "paperless_tags": { "type": "array", "items": { "type": "string" } },
        "paperless_correspondent": { "type": "string" },
        "paperless_created_year": { "type": "integer" },
        "paperless_document_type": { "type": "string" }
      },
      "required": ["query"]
    }
  },
  {
    "name": "keyword_search_notes",
    "description": "Exact keyword search in filenames and content. Multi-word queries use AND logic. Best for abbreviations, URLs, identifiers, class names, and enum values. Supports Paperless filters.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "top_k": { "type": "integer", "default": 5 },
        "paperless_tags": { "type": "array", "items": { "type": "string" } },
        "paperless_correspondent": { "type": "string" },
        "paperless_created_year": { "type": "integer" },
        "paperless_document_type": { "type": "string" }
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
      "description": "Semantic search in the Obsidian vault and Paperless-NGX. Best for concepts, explanations, broad topics, and fuzzy user questions. Supports Paperless metadata filters and optional newest-first sorting.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results." },
          "expand_links": { "type": "boolean", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags." },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." },
          "sort_by_date": { "type": "boolean", "description": "Sort newest-first by creation date instead of by score." },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive)." },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year." },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
        },
        "required": ["query"]
      }
    },
    {
      "name": "hybrid_search_notes",
      "description": "Hybrid search that combines semantic and keyword search, then merges and reranks results. Best default for natural-language queries that also contain specific identifiers or Paperless document language.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Natural-language search query." },
          "top_k": { "type": "integer", "description": "Maximum number of results." },
          "min_score": { "type": "number", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions." },
          "sort_by_date": { "type": "boolean", "description": "Sort newest-first by creation date instead of by score." },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive)." },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year." },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
        },
        "required": ["query"]
      }
    },
    {
      "name": "keyword_search_notes",
      "description": "Exact keyword search in filenames and content. Multi-word queries use AND logic. Best for abbreviations, URLs, identifiers, class names, and enum values. Supports Paperless filters.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Exact search string." },
          "top_k": { "type": "integer", "description": "Maximum number of results." },
          "paperless_tags": { "type": "array", "items": { "type": "string" }, "description": "Filter Paperless documents by tag names (exact match, case-insensitive)." },
          "paperless_correspondent": { "type": "string", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive)." },
          "paperless_created_year": { "type": "integer", "description": "Filter Paperless documents by creation year." },
          "paperless_document_type": { "type": "string", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\"." }
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
    "description": "Semantic search in the Obsidian vault and Paperless-NGX. Best for concepts, explanations, broad topics, and fuzzy user questions. Supports Paperless metadata filters and optional newest-first sorting.",
    "parameter_definitions": {
      "query": { "type": "str", "description": "Natural-language search query.", "required": true },
      "top_k": { "type": "int", "description": "Maximum number of results.", "required": false },
      "expand_links": { "type": "bool", "description": "Include graph-boosted related notes via wikilinks, backlinks, and tags.", "required": false },
      "min_score": { "type": "float", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions.", "required": false },
      "sort_by_date": { "type": "bool", "description": "Sort newest-first by creation date instead of by score.", "required": false },
      "paperless_tags": { "type": "list[str]", "description": "Filter Paperless documents by tag names (exact match, case-insensitive).", "required": false },
      "paperless_correspondent": { "type": "str", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive).", "required": false },
      "paperless_created_year": { "type": "int", "description": "Filter Paperless documents by creation year.", "required": false },
      "paperless_document_type": { "type": "str", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\".", "required": false }
    }
  },
  {
    "name": "hybrid_search_notes",
    "description": "Hybrid search that combines semantic and keyword search, then merges and reranks results. Best default for natural-language queries that also contain specific identifiers or Paperless document language.",
    "parameter_definitions": {
      "query": { "type": "str", "description": "Natural-language search query.", "required": true },
      "top_k": { "type": "int", "description": "Maximum number of results.", "required": false },
      "min_score": { "type": "float", "description": "Optional minimum relevance threshold. Recommended 0.70 for precise questions.", "required": false },
      "sort_by_date": { "type": "bool", "description": "Sort newest-first by creation date instead of by score.", "required": false },
      "paperless_tags": { "type": "list[str]", "description": "Filter Paperless documents by tag names (exact match, case-insensitive).", "required": false },
      "paperless_correspondent": { "type": "str", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive).", "required": false },
      "paperless_created_year": { "type": "int", "description": "Filter Paperless documents by creation year.", "required": false },
      "paperless_document_type": { "type": "str", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\".", "required": false }
    }
  },
  {
    "name": "keyword_search_notes",
    "description": "Exact keyword search in filenames and content. Multi-word queries use AND logic. Best for abbreviations, URLs, identifiers, class names, and enum values. Supports Paperless filters.",
    "parameter_definitions": {
      "query": { "type": "str", "description": "Exact search string.", "required": true },
      "top_k": { "type": "int", "description": "Maximum number of results.", "required": false },
      "paperless_tags": { "type": "list[str]", "description": "Filter Paperless documents by tag names (exact match, case-insensitive).", "required": false },
      "paperless_correspondent": { "type": "str", "description": "Filter Paperless documents by correspondent name (exact match, case-insensitive).", "required": false },
      "paperless_created_year": { "type": "int", "description": "Filter Paperless documents by creation year.", "required": false },
      "paperless_document_type": { "type": "str", "description": "Filter Paperless documents by document type name, e.g. \"Rechnung\" or \"Vertrag\".", "required": false }
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

- Call `get_filters` (`GET /filters`) at the start of a session to discover available tags, document types, and correspondents.
- For Paperless-related queries, always set the strongest available `paperless_*` filters first, then run search only on that filtered result set.
- Use `keyword_search_notes` first for abbreviations, URLs, hostnames, model numbers, code symbols, and exact identifiers.
- Use `hybrid_search_notes` as the default for natural-language queries that also contain concrete business terms, names, or likely exact identifiers.
- Use `search_notes` for meanings, concepts, explanations, and topic-based questions.
- For relevant results, fetch the full context with `get_note`.
- Use `min_score: 0.70` as the default for precise questions.
- If the user asks for the latest, newest, or most recent document, set `sort_by_date: true`.
- If `search_notes` unexpectedly returns empty: often an identifier issue → try `keyword_search_notes` or `hybrid_search_notes`.

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
- For cloud agents, replace `http://127.0.0.1:8484` with a reachable `https` URL.
- Without HTTP/tool access, `SKILL.md` is only a behavioral guide, not a real connection to the API.

## Available Endpoints

### 1. Semantic Search

Searches for semantically similar note sections. Also returns linked and tag-connected notes (`expand_links: true`).

Use `min_score` to filter out irrelevant results (recommended: `0.72` for precise questions, `0.65` for broad topics).

```bash
curl -s http://127.0.0.1:8484/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the heat pump work?", "top_k": 5, "min_score": 0.70}'
```

**With Paperless filters** (always pre-filter Paperless first, then rank semantically on the filtered set):
```bash
curl -s http://127.0.0.1:8484/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "alle Kosten", "top_k": 10, "paperless_tags": ["etron"], "paperless_created_year": 2025}'
```

**Newest-first Paperless search**:
```bash
curl -s http://127.0.0.1:8484/search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "letzte Rechnung", "top_k": 5, "sort_by_date": true, "paperless_document_type": "Rechnung"}'
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

Multi-word queries use AND logic, so `"kaufvertrag grundstück"` only matches documents containing both terms.

```bash
curl -s http://127.0.0.1:8484/keyword-search \
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

### 3. Hybrid Search

Combines semantic and keyword search, merges the result sets, deduplicates them, and reranks by combined relevance.

Use this as the default for natural-language questions that also contain concrete identifiers or document language, for example company names, invoice/document terms, car models, or locations.

For Paperless-related questions, always set the strongest available Paperless filters first, then run hybrid search on that pre-filtered document set.

```bash
curl -s http://127.0.0.1:8484/hybrid-search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Kaufvertrag Grundstück Montabaur", "top_k": 5, "min_score": 0.70}'
```

**With Paperless filters and newest-first sorting**:
```bash
curl -s http://127.0.0.1:8484/hybrid-search \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "letzte Telekom Rechnung", "top_k": 5, "sort_by_date": true, "paperless_correspondent": "Telekom", "paperless_document_type": "Rechnung"}'
```

### 4. Retrieve a Note

Returns the full Markdown content of a single note.

```bash
curl -s "http://127.0.0.1:8484/note?path=Home/Heating/Heatpump.md" \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

**POST variant** (for agents that use POST for all endpoints, e.g. n8n HTTP Request Tool):

```bash
curl -s http://127.0.0.1:8484/note \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "Home/Heating/Heatpump.md"}'
```

### 5. Available Filters

Returns all known Paperless tags, document types, and correspondents. Call this once at the start of a session to discover which filter values are available for `paperless_tags`, `paperless_document_type`, and `paperless_correspondent`.

```bash
curl -s http://127.0.0.1:8484/filters \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

**Response:**
```json
{
  "tags": ["auto", "banking", "duong", "etron", "golf7", "lina", "rechnung"],
  "document_types": ["bescheinigung", "rechnung", "vertrag"],
  "correspondents": ["dkb", "ing diba", "telekom"]
}
```

### 6. Trigger Reindex

```bash
curl -s -X POST http://127.0.0.1:8484/reindex \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

### 7. Indexing Status

```bash
curl -s http://127.0.0.1:8484/status \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
# → {"indexing": false, "indexed_files": 95}
```

### 8. Statistics

```bash
curl -s http://127.0.0.1:8484/stats \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
# → {"total_chunks": 187, "total_files": 95, "link_graph_edges": 42}
```

### 9. Health Check

```bash
curl -s http://127.0.0.1:8484/health
```

## Search Strategy for Agents

### Which Search to Use?

| Question type | Method | Example |
|---|---|---|
| Concept, meaning, explanation | `/search` | "How does X work?" |
| Natural language with specific names/terms | `/hybrid-search` | "Kaufvertrag Grundstück Montabaur" |
| Short abbreviation / acronym | `/keyword-search` | `"NVR"`, `"VPN"`, `"PoE"` |
| Hostname / container name | `/keyword-search` | `"homeassistant"`, `"pihole"` |
| IP address / port | `/keyword-search` | `"192.168.1.1"`, `"8080"` |
| Model / product name | `/keyword-search` | `"USG-3P"`, `"EVO Plus"` |
| Version number / date ID | `/keyword-search` | `"v3.2.1"`, `"2024-03-15"` |
| Configuration key | `/keyword-search` | `"VAULT_PATH"`, `"hnsw:space"` |
| Class names, enum values | `/keyword-search` | `"SensorType"`, `"ContentType"` |
| Broad topic with context | `/search` with `top_k: 10` | "Everything about network segmentation" |
| Specific file known | `/note` | direct path |
| Latest or newest Paperless docs | `paperless_*` filters first, then `/search` or `/hybrid-search` with `sort_by_date: true` | `"letzte Rechnung"` |
| Paperless docs by tag/year/correspondent/type | `paperless_*` filters first, then `/search` or `/hybrid-search` | `paperless_tags: ["etron"]` |

### When to Use Paperless Filters

Use `paperless_tags`, `paperless_correspondent`, `paperless_created_year`, or `paperless_document_type` when the user's question implies structured criteria that map to Paperless metadata.

For Paperless-related questions, these filters are the first step, not optional tuning. Apply the strongest available filters before any RAG search so semantic or hybrid ranking runs only on the pre-filtered Paperless subset:

| User says | Filter to set |
|---|---|
| "alle Rechnungen für Audi e-tron in 2025" | `paperless_tags: ["etron"]`, `paperless_created_year: 2025` |
| "Dokumente von Stadtwerke" | `paperless_correspondent: "Stadtwerke"` |
| "Versicherungsdokumente 2024" | `paperless_tags: ["versicherung"]`, `paperless_created_year: 2024` |
| "Rechnungen von Telekom letztes Jahr" | `paperless_correspondent: "Telekom"`, `paperless_created_year: 2025` |
| "letzte Rechnung von Telekom" | `paperless_correspondent: "Telekom"`, `paperless_document_type: "Rechnung"`, `sort_by_date: true` |
| "alle Verträge aus 2024" | `paperless_document_type: "Vertrag"`, `paperless_created_year: 2024` |

**How it works:** When Paperless credentials are configured, filters are resolved through the Paperless API first and then mapped to matching `paperless_doc_id` values. This is more accurate than relying on embedded text alone and supports document type filters cleanly. If the API is unavailable, the search falls back to ChromaDB metadata filters.

**When NOT to use filters:** If the question is purely conceptual ("How does X work?") or doesn't reference specific Paperless tags, correspondents, or time periods, omit the filters entirely — they would unnecessarily restrict results.

### Recommended Order for Ambiguous Questions

1. If the question is about Paperless documents, extract and set the strongest available `paperless_*` filters first.
2. If the user asks for the latest/newest/most recent Paperless result, also set `sort_by_date: true`.
3. If the question contains an identifier only (abbreviation, hostname, model name, ID, version number), use `/keyword-search`.
4. If the question mixes natural language with exact names, entities, or document terms, use `/hybrid-search` with `min_score: 0.70`.
5. Otherwise use `/search` with `min_score: 0.70`.
6. For relevant results, fetch full context with `/note`.
7. If empty, retry `/search` or `/hybrid-search` with `min_score: 0.60` and `top_k: 10`.
8. If still empty, try `/keyword-search`.

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

Question: *"Summiere alle Kosten für Audi e-tron in 2025"*
```
1. hybrid-search("Kosten Rechnung Audi e-tron", paperless_tags=["etron"], paperless_created_year=2025, top_k=20)
   → pre-filters Paperless docs by tag + year, then combines semantic and exact-term relevance
2. get_note(<file_path>)   → loads full content for each result to extract amounts
```

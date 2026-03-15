#!/bin/bash
# RAG API – Setup & Start Script
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

# ── Defaults (single source of truth) ────────────────────────────────────
_DEFAULT_BIND="127.0.0.1"
_DEFAULT_PORT="8484"
_DEFAULT_OLLAMA_SERVICE="ollama"
_DEFAULT_RAG_API_SERVICE="rag-api"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Helpers ───────────────────────────────────────────────────────────────
# die() must be defined before argument parsing so unknown flags print a proper error.

die() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

# _update_env KEY VALUE [KEY VALUE …]  –  atomically update key=value pairs in .env
_update_env() {
  local args=()
  while [[ $# -ge 2 ]]; do
    args+=(-e "s|^$1=.*|$1=$2|")
    shift 2
  done
  sed -i.bak "${args[@]}" .env && rm -f .env.bak
}

_summary() {
  if [[ "${ACCESS_MODE:-host}" == "host" ]]; then
    echo -e "   API:     ${BLUE}http://${HOST_BIND_ADDRESS:-$_DEFAULT_BIND}:${HOST_PORT:-$_DEFAULT_PORT}${NC}"
  else
    echo -e "   API:     ${BLUE}internal Docker network only${NC}"
    echo -e "   Network: ${BOLD}${DOCKER_NETWORK:-rag-network}${NC}"
  fi
  echo -e "   Logs:    ${BOLD}docker compose logs -f ${_DEFAULT_RAG_API_SERVICE}${NC}"
  echo -e "   Stop:    ${BOLD}docker compose down${NC}"
}

_bar_str() {
  local cur=$1 tot=$2 w=30
  if [ "$tot" -le 0 ]; then
    printf '⏳ %d files indexed...' "$cur"; return
  fi
  local pct=$(( cur * 100 / tot ))
  local f=$(( cur * w / tot ))
  local e=$(( w - f ))
  local bar_f="" bar_e=""
  [ "$f" -gt 0 ] && bar_f=$(printf '%0.s█' $(seq 1 "$f"))
  [ "$e" -gt 0 ] && bar_e=$(printf '%0.s░' $(seq 1 "$e"))
  printf '[%s%s] %d/%d (%d%%)' "$bar_f" "$bar_e" "$cur" "$tot" "$pct"
}

_draw_bar() {
  printf '\r\033[K   '
  _bar_str "$1" "$2"
}

_json_int() {
  # _json_int "$json_string" "field_name" → integer or 0
  echo "$1" | grep -o "\"$2\":[0-9]*" | grep -o '[0-9]*' | head -1 || echo "0"
}

_compose() {
  local files=(-f docker-compose.yml)
  [[ "${DATA_SOURCES:-all}" != "paperless" ]] && files+=(-f docker-compose.obsidian.yml)
  [[ "${ACCESS_MODE:-host}" == "host" ]] && files+=(-f docker-compose.host.yml)
  if [[ "${DATA_SOURCES:-all}" != "obsidian" ]] && [[ -n "${PAPERLESS_ARCHIVE_PATH:-}" ]] && [[ -d "${PAPERLESS_ARCHIVE_PATH}" ]]; then
    files+=(-f docker-compose.paperless.yml)
  fi
  docker compose "${files[@]}" "$@"
}

_validate_config() {
  if [[ "${DATA_SOURCES:-all}" != "paperless" ]]; then
    [[ -n "${VAULT_PATH:-}" ]] || die "VAULT_PATH is required when DATA_SOURCES=${DATA_SOURCES:-all}."
    [[ -d "${VAULT_PATH}" ]]   || die "VAULT_PATH does not exist: ${VAULT_PATH}"
  fi
}

_api_get() {
  local path=$1
  if [[ "${ACCESS_MODE:-host}" == "host" ]]; then
    local url="http://${HOST_BIND_ADDRESS:-$_DEFAULT_BIND}:${HOST_PORT:-$_DEFAULT_PORT}${path}"
    local -a curl_args=(-sf)
    [[ "${AUTH_REQUIRED:-true}" == "true" ]] && curl_args+=(-H "Authorization: Bearer ${API_BEARER_TOKEN}")
    curl "${curl_args[@]}" "$url"
  else
    _compose exec -T "${_DEFAULT_RAG_API_SERVICE}" python -c '
import sys, urllib.request
path = sys.argv[1]
token = sys.argv[2]
req = urllib.request.Request("http://127.0.0.1:8080" + path)
if token:
    req.add_header("Authorization", "Bearer " + token)
with urllib.request.urlopen(req, timeout=5) as resp:
    sys.stdout.write(resp.read().decode())
' "$path" "${API_BEARER_TOKEN:-}"
  fi
}

# ── Shared prompt helpers (used by both fresh setup and .env reuse) ───────

_prompt_vault_path() {
  while true; do
    printf "📁 Path to your vault ${BLUE}(directory containing .md files)${NC}: "
    read -r VAULT_PATH
    VAULT_PATH="${VAULT_PATH/#\~/$HOME}"
    if [[ -d "$VAULT_PATH" ]]; then
      VAULT_PATH="$(cd "$VAULT_PATH" && pwd)"
      echo -e "   ${GREEN}✓${NC} $VAULT_PATH\n"
      return 0
    fi
    echo -e "${RED}❌ Directory not found: $VAULT_PATH${NC}"
  done
}

_prompt_paperless_path() {
  # Sets PAPERLESS_ARCHIVE_PATH; empty string means the user chose to skip.
  while true; do
    printf "📂 Path to Paperless archive/ directory ${BLUE}(leave empty to skip)${NC}: "
    read -r PAPERLESS_ARCHIVE_PATH
    PAPERLESS_ARCHIVE_PATH="${PAPERLESS_ARCHIVE_PATH/#\~/$HOME}"
    if [[ -z "$PAPERLESS_ARCHIVE_PATH" ]]; then
      if [[ "$DATA_SOURCES" == "paperless" ]]; then
        echo -e "   ${YELLOW}⚠️  Paperless archive skipped – no Paperless documents will be indexed.${NC}\n"
      else
        echo -e "   ${YELLOW}⚠️  Paperless archive skipped – only Obsidian will be indexed.${NC}\n"
      fi
      return 0
    fi
    if [[ -d "$PAPERLESS_ARCHIVE_PATH" ]]; then
      PAPERLESS_ARCHIVE_PATH="$(cd "$PAPERLESS_ARCHIVE_PATH" && pwd)"
      echo -e "   ${GREEN}✓${NC} $PAPERLESS_ARCHIVE_PATH\n"
      return 0
    fi
    echo -e "${RED}❌ Directory not found: $PAPERLESS_ARCHIVE_PATH${NC}"
  done
}

_prompt_paperless_api() {
  # Sets PAPERLESS_URL, PAPERLESS_TOKEN, PAPERLESS_PUBLIC_URL (all may remain empty).
  echo -n "🌐 Paperless URL for API enrichment (title/tags) [leave empty to skip]: "
  read -r PAPERLESS_URL
  if [[ -n "$PAPERLESS_URL" ]]; then
    echo -n "🔑 Paperless API token: "
    read -rs PAPERLESS_TOKEN; echo ""
    echo -e "   ${BLUE}ℹ️  Public URL${NC}: Used to build direct links in search results so n8n/agents"
    echo -e "      can open the source document in your Paperless UI."
    echo -e "      ${YELLOW}Leave empty${NC} to omit links – results will then only show the filename."
    echo -n "🔗 Paperless public URL (e.g. https://paperless.example.com) [leave empty to skip]: "
    read -r PAPERLESS_PUBLIC_URL
    echo -e "   ${GREEN}✓${NC} Paperless: $PAPERLESS_URL\n"
  fi
}

# ── Argument parsing ──────────────────────────────────────────────────────
DATA_SOURCES="all"
for arg in "$@"; do
  case "$arg" in
    --obsidian-only)  DATA_SOURCES="obsidian"  ;;
    --paperless-only) DATA_SOURCES="paperless" ;;
    *) die "Unknown argument: $arg\nUsage: ./start.sh [--obsidian-only | --paperless-only]" ;;
  esac
done

# ── Prerequisites ─────────────────────────────────────────────────────────

docker info > /dev/null 2>&1 || die "Docker is not running. Please start the Docker daemon and try again."

echo -e "${BOLD}🚀 RAG API – Setup${NC}\n"

# ── Interactive setup (skipped when an existing .env is reused) ───────────

_run_setup() {
  local generated_token=""
  local ollama_service_name=""
  PAPERLESS_URL="" PAPERLESS_TOKEN="" PAPERLESS_PUBLIC_URL="" PAPERLESS_ARCHIVE_PATH=""

  # 1. Vault path – only when indexing Obsidian
  if [[ "$DATA_SOURCES" != "paperless" ]]; then
    _prompt_vault_path
  else
    VAULT_PATH=""
  fi

  # 2. Paperless config – only when indexing Paperless
  if [[ "$DATA_SOURCES" != "obsidian" ]]; then
    _prompt_paperless_path
    [[ -n "$PAPERLESS_ARCHIVE_PATH" ]] && _prompt_paperless_api
  fi

  # 3. Ollama – local or external?
  echo -n "🦙 Is Ollama already running externally? [y/N] "
  read -r USE_EXTERNAL

  if [[ "$USE_EXTERNAL" =~ ^[yYjJ]$ ]]; then
    echo -n "   Docker service/container name on the shared network [${_DEFAULT_OLLAMA_SERVICE}]: "
    read -r ollama_service_name
    ollama_service_name="${ollama_service_name:-$_DEFAULT_OLLAMA_SERVICE}"
    echo -n "   Override URL [http://${ollama_service_name}:11434, leave empty to use the service name]: "
    read -r OLLAMA_URL
    OLLAMA_URL="${OLLAMA_URL:-http://${ollama_service_name}:11434}"
    COMPOSE_PROFILES=""
    LOCAL_OLLAMA=false
    echo -e "   ${GREEN}✓${NC} Using external Ollama: $OLLAMA_URL\n"
  else
    OLLAMA_URL="http://${_DEFAULT_OLLAMA_SERVICE}:11434"
    COMPOSE_PROFILES="local-ollama"
    LOCAL_OLLAMA=true
    echo -e "   ${GREEN}✓${NC} Local Ollama will be started\n"
  fi

  # 4. Access mode
  HOST_BIND_ADDRESS="$_DEFAULT_BIND"
  HOST_PORT="$_DEFAULT_PORT"
  echo -n "🌐 Publish API on the host ($_DEFAULT_BIND:$_DEFAULT_PORT)? [Y/n] "
  read -r PUBLISH_HOST

  if [[ "$PUBLISH_HOST" =~ ^[nN]$ ]]; then
    ACCESS_MODE="internal"
    PUBLIC_URL="http://rag-api:8080"
    echo -n "🔐 Require bearer token for internal-only mode? [y/N] "
    read -r REQUIRE_AUTH
    if [[ "$REQUIRE_AUTH" =~ ^[yYjJ]$ ]]; then
      AUTH_REQUIRED="true"
      generated_token="$(openssl rand -hex 32)"
      echo -e "   ${GREEN}✓${NC} Internal-only mode with bearer token\n"
    else
      AUTH_REQUIRED="false"
      echo -e "   ${GREEN}✓${NC} Internal-only mode, no authentication (trusted network)\n"
    fi
  else
    ACCESS_MODE="host"
    PUBLIC_URL="http://localhost:$_DEFAULT_PORT"
    echo -n "🔐 Require bearer token? [Y/n] "
    read -r REQUIRE_AUTH
    if [[ "$REQUIRE_AUTH" =~ ^[nN]$ ]]; then
      AUTH_REQUIRED="false"
      echo -e "   ${YELLOW}⚠️  Authentication disabled – API is open to anyone who can reach port ${HOST_PORT}.${NC}"
      echo -e "   ${YELLOW}   Only use this for local testing.${NC}\n"
    else
      AUTH_REQUIRED="true"
      generated_token="$(openssl rand -hex 32)"
      echo -e "   ${GREEN}✓${NC} Host access enabled at http://${HOST_BIND_ADDRESS}:${HOST_PORT}\n"
    fi
  fi

  # 5. Docker network (optional)
  echo -n "🔗 External Docker network to join (leave empty for default 'rag-network'): "
  read -r DOCKER_NETWORK
  if [[ -n "$DOCKER_NETWORK" ]]; then
    echo -e "   ${GREEN}✓${NC} Will join network: $DOCKER_NETWORK\n"
  else
    DOCKER_NETWORK=""
    echo -e "   ${GREEN}✓${NC} Using default network: rag-network\n"
  fi

  # 6. Write .env
  cat > .env <<EOF
DATA_SOURCES=$DATA_SOURCES
VAULT_PATH=$VAULT_PATH
OLLAMA_URL=$OLLAMA_URL
COMPOSE_PROFILES=$COMPOSE_PROFILES
ACCESS_MODE=$ACCESS_MODE
HOST_BIND_ADDRESS=$HOST_BIND_ADDRESS
HOST_PORT=$HOST_PORT
PUBLIC_URL=$PUBLIC_URL
AUTH_REQUIRED=$AUTH_REQUIRED
API_BEARER_TOKEN=$generated_token
DOCKER_NETWORK=$DOCKER_NETWORK
PAPERLESS_ARCHIVE_PATH=$PAPERLESS_ARCHIVE_PATH
PAPERLESS_URL=$PAPERLESS_URL
PAPERLESS_TOKEN=$PAPERLESS_TOKEN
PAPERLESS_PUBLIC_URL=$PAPERLESS_PUBLIC_URL
EOF
  echo -e "${GREEN}✅ .env created${NC}\n"
  if [[ "$AUTH_REQUIRED" == "true" ]]; then
    echo -e "${BOLD}🔐 API bearer token${NC}"
    echo -e "   $generated_token"
    echo -e "   Save this token. Clients must send: ${BOLD}Authorization: Bearer <token>${NC}\n"
  else
    echo -e "${YELLOW}🔓 Authentication disabled.${NC}\n"
  fi
}

# ── Check for existing .env with a valid vault path ───────────────────────

if [[ -f .env ]]; then
  EXISTING_VAULT=$(grep -E '^VAULT_PATH=' .env | cut -d= -f2-)
  EXISTING_PAPERLESS=$(grep -E '^PAPERLESS_ARCHIVE_PATH=' .env | cut -d= -f2-)
  _env_valid=false
  [[ -n "$EXISTING_VAULT"     && -d "$EXISTING_VAULT"     ]] && _env_valid=true
  [[ -n "$EXISTING_PAPERLESS" && -d "$EXISTING_PAPERLESS" ]] && _env_valid=true

  if [[ "$_env_valid" == true ]]; then
    echo -e "${BOLD}📄 Existing .env found:${NC}"
    grep -v '^#' .env | grep -v '^[[:space:]]*$' | while IFS='=' read -r key val; do
      echo -e "   ${BLUE}${key}${NC}=${val}"
    done
    echo ""
    echo -n "♻️  Use this configuration? [Y/n] "
    read -r REUSE
    echo ""

    if [[ "$REUSE" =~ ^[nN]$ ]]; then
      _run_setup
    else
      # Load values from existing .env
      _cli_data_sources="$DATA_SOURCES"
      set -a; source .env; set +a
      # CLI flag always wins over the stored value.
      # A bare invocation (no flag → "all") also resets the stored value so that
      # e.g. a previous --obsidian-only run doesn't silently stay obsidian-only.
      DATA_SOURCES="$_cli_data_sources"
      ACCESS_MODE="${ACCESS_MODE:-host}"
      HOST_BIND_ADDRESS="${HOST_BIND_ADDRESS:-$_DEFAULT_BIND}"
      HOST_PORT="${HOST_PORT:-$_DEFAULT_PORT}"
      DOCKER_NETWORK="${DOCKER_NETWORK:-}"
      PAPERLESS_ARCHIVE_PATH="${PAPERLESS_ARCHIVE_PATH:-}"
      if [[ "$ACCESS_MODE" == "host" ]]; then
        PUBLIC_URL="${PUBLIC_URL:-http://${HOST_BIND_ADDRESS}:${HOST_PORT}}"
        AUTH_REQUIRED="${AUTH_REQUIRED:-true}"
      else
        PUBLIC_URL="${PUBLIC_URL:-http://${_DEFAULT_RAG_API_SERVICE}:8080}"
        AUTH_REQUIRED="${AUTH_REQUIRED:-false}"
      fi

      # Mint a new token if auth is required but none exists yet
      if [[ "${AUTH_REQUIRED}" == "true" && -z "${API_BEARER_TOKEN:-}" ]]; then
        API_BEARER_TOKEN="$(openssl rand -hex 32)"
        printf '\nAPI_BEARER_TOKEN=%s\n' "$API_BEARER_TOKEN" >> .env
        echo -e "${YELLOW}⚠️  No API token found in .env – a new token was added.${NC}"
        echo -e "   ${BOLD}${API_BEARER_TOKEN}${NC}\n"
      fi

      # Persist effective DATA_SOURCES back to .env
      _update_env DATA_SOURCES "$DATA_SOURCES"

      # ── Fill in any paths that are now required but missing ──────────────
      # This happens when e.g. the first run used --obsidian-only and the second
      # run uses no flag (→ all), so Paperless was never configured.

      # Vault path needed but missing
      if [[ "$DATA_SOURCES" != "paperless" && (-z "${VAULT_PATH:-}" || ! -d "${VAULT_PATH:-}") ]]; then
        echo -e "${YELLOW}⚠️  VAULT_PATH is missing or invalid. Please provide it now.${NC}"
        _prompt_vault_path
        _update_env VAULT_PATH "$VAULT_PATH"
      fi

      # Paperless archive path needed but missing
      if [[ "$DATA_SOURCES" != "obsidian" && (-z "${PAPERLESS_ARCHIVE_PATH:-}" || ! -d "${PAPERLESS_ARCHIVE_PATH:-}") ]]; then
        echo -e "${YELLOW}⚠️  PAPERLESS_ARCHIVE_PATH is missing or invalid. Please provide it now.${NC}"
        _prompt_paperless_path
        if [[ -z "$PAPERLESS_ARCHIVE_PATH" ]]; then
          DATA_SOURCES="obsidian"
          _update_env DATA_SOURCES "obsidian"
        else
          _update_env PAPERLESS_ARCHIVE_PATH "$PAPERLESS_ARCHIVE_PATH"
          # Also prompt for API URL + token if not yet configured
          if [[ -z "${PAPERLESS_URL:-}" ]]; then
            _prompt_paperless_api
            _update_env \
              PAPERLESS_URL          "$PAPERLESS_URL" \
              PAPERLESS_TOKEN        "$PAPERLESS_TOKEN" \
              PAPERLESS_PUBLIC_URL   "$PAPERLESS_PUBLIC_URL"
          fi
        fi
      fi

      LOCAL_OLLAMA=false
      [[ "${COMPOSE_PROFILES:-}" == *"local-ollama"* ]] && LOCAL_OLLAMA=true
      echo -e "${GREEN}✅ Using existing .env${NC}\n"
    fi
  else
    # .env exists but no valid vault/paperless path found → run setup
    _run_setup
  fi
else
  _run_setup
fi

_validate_config

# Ensure the Docker network exists before starting containers.
# This is a no-op if the network already exists (e.g. created by n8n).
docker network create "${DOCKER_NETWORK:-rag-network}" > /dev/null 2>&1 || true

# ── Start Ollama & pull model (local only) ────────────────────────────────
if [[ "$LOCAL_OLLAMA" == true ]]; then
  echo "🦙 Starting Ollama container..."
  _compose --profile local-ollama up -d "${_DEFAULT_OLLAMA_SERVICE}"

  echo "⏳ Waiting for Ollama API..."
  attempts=0
  until _compose exec -T "${_DEFAULT_OLLAMA_SERVICE}" ollama list > /dev/null 2>&1; do
    sleep 2
    attempts=$(( attempts + 1 ))
    [ "$attempts" -ge 60 ] && die "Ollama did not respond after 2 minutes. Check: docker compose logs ${_DEFAULT_OLLAMA_SERVICE}"
  done

  echo "📥 Pulling nomic-embed-text (first run: ~1 min)..."
  _compose exec -T "${_DEFAULT_OLLAMA_SERVICE}" ollama pull nomic-embed-text
  echo -e "${GREEN}✅ Model ready${NC}\n"
fi

# ── Start rag-api ─────────────────────────────────────────────────────────
echo "🐳 Starting rag-api..."
_compose up -d "${_DEFAULT_RAG_API_SERVICE}" || die "docker compose failed. Check: docker compose logs ${_DEFAULT_RAG_API_SERVICE}"
echo ""

# ── Wait for indexing (Ctrl+C skips, containers keep running) ────────────
trap 'printf "\n\n"; echo -e "${YELLOW}⏳ Indexing continues in the background.${NC}"; _summary; exit 0' INT

echo -e "${YELLOW}⏳ Waiting for indexing...${NC} ${BOLD}(Ctrl+C to skip)${NC}"

until _api_get /health > /dev/null 2>&1; do
  printf '\r\033[K   Starting API...'
  sleep 2
done

_PROGRESS_LINES=0
INDEXED=0
while true; do
  STATUS=$(_api_get /status 2>/dev/null || echo "{}")
  INDEXED=$(_json_int "$STATUS" "indexed_files")
  TOTAL=$(_json_int  "$STATUS" "total_files")

  if echo "$STATUS" | grep -q '"indexing":false'; then
    [[ $_PROGRESS_LINES -gt 0 ]] && printf '\033[%dA\r\033[J' "$_PROGRESS_LINES"
    echo -e "${GREEN}✅ RAG API ready! ${INDEXED} files indexed.${NC}"
    break
  fi

  if [[ "${DATA_SOURCES:-all}" == "all" && -n "${PAPERLESS_ARCHIVE_PATH:-}" ]]; then
    OBS_IDX=$(_json_int "$STATUS" "obsidian_indexed")
    OBS_TOT=$(_json_int "$STATUS" "obsidian_total")
    PAP_IDX=$(_json_int "$STATUS" "paperless_indexed")
    PAP_TOT=$(_json_int "$STATUS" "paperless_total")
    [[ $_PROGRESS_LINES -gt 0 ]] && printf '\033[%dA' "$_PROGRESS_LINES"
    _PROGRESS_LINES=2
    printf '\r\033[K   Obsidian:  '; _bar_str "$OBS_IDX" "$OBS_TOT"; printf '\n'
    printf '\r\033[K   Paperless: '; _bar_str "$PAP_IDX" "$PAP_TOT"
  else
    _PROGRESS_LINES=1
    _draw_bar "$INDEXED" "$TOTAL"
  fi
  sleep 2
done

trap - INT

echo ""
_summary
echo ""

if command -v osascript > /dev/null 2>&1; then
  osascript -e "display notification \"${INDEXED} files indexed\" with title \"RAG API ready\" sound name \"Glass\"" 2>/dev/null &
elif command -v notify-send > /dev/null 2>&1; then
  notify-send "RAG API ready" "${INDEXED} files indexed" 2>/dev/null &
fi

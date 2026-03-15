#!/bin/bash
# RAG API – Setup & Start Script
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Helpers ───────────────────────────────────────────────────────────────

die() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

_summary() {
  if [[ "${ACCESS_MODE:-host}" == "host" ]]; then
    echo -e "   API:     ${BLUE}http://${HOST_BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8484}${NC}"
  else
    echo -e "   API:     ${BLUE}internal Docker network only${NC}"
    echo -e "   Network: ${BOLD}${DOCKER_NETWORK:-rag-network}${NC}"
  fi
  echo -e "   Logs:    ${BOLD}docker logs -f rag-api${NC}"
  echo -e "   Stop:    ${BOLD}docker compose down${NC}"
}

_draw_bar() {
  local cur=$1 tot=$2 w=30
  if [ "$tot" -le 0 ]; then
    printf '\r\033[K   ⏳ %d files indexed...' "$cur"; return
  fi
  local pct=$(( cur * 100 / tot ))
  local f=$(( cur * w / tot ))
  local e=$(( w - f ))
  local bar_f="" bar_e=""
  [ "$f" -gt 0 ] && bar_f=$(printf '%0.s█' $(seq 1 "$f"))
  [ "$e" -gt 0 ] && bar_e=$(printf '%0.s░' $(seq 1 "$e"))
  printf '\r\033[K   [%s%s] %d/%d (%d%%)' "$bar_f" "$bar_e" "$cur" "$tot" "$pct"
}

_json_int() {
  # _json_int "$json_string" "field_name" → integer or 0
  echo "$1" | grep -o "\"$2\":[0-9]*" | grep -o '[0-9]*' || echo "0"
}

_compose() {
  if [[ "${ACCESS_MODE:-host}" == "host" ]]; then
    docker compose -f docker-compose.yml -f docker-compose.host.yml "$@"
  else
    docker compose -f docker-compose.yml "$@"
  fi
}

_api_get() {
  local path=$1
  if [[ "${ACCESS_MODE:-host}" == "host" ]]; then
    local url="http://${HOST_BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8484}${path}"
    if [[ "${AUTH_REQUIRED:-true}" == "true" ]]; then
      curl -sf -H "Authorization: Bearer ${API_BEARER_TOKEN}" "$url"
    else
      curl -sf "$url"
    fi
  else
    docker exec rag-api python -c '
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

# ── Prerequisites ─────────────────────────────────────────────────────────

docker info > /dev/null 2>&1 || die "Docker Desktop is not running. Please start it and try again."

echo -e "${BOLD}🚀 RAG API – Setup${NC}\n"

# ── Interactive setup (skipped when an existing .env is reused) ───────────

_run_setup() {
  local generated_token

  # 1. Vault path
  while true; do
    printf "📁 Path to your vault ${BLUE}(directory containing .md files)${NC}: "
    read -r VAULT_PATH
    VAULT_PATH="${VAULT_PATH/#\~/$HOME}"
    if [[ -d "$VAULT_PATH" ]]; then
      VAULT_PATH="$(cd "$VAULT_PATH" && pwd)"
      echo -e "   ${GREEN}✓${NC} $VAULT_PATH\n"
      break
    fi
    echo -e "${RED}❌ Directory not found: $VAULT_PATH${NC}"
  done

  # 2. Ollama – local or external?
  echo -n "🦙 Is Ollama already running externally? [y/N] "
  read -r USE_EXTERNAL

  if [[ "$USE_EXTERNAL" =~ ^[yYjJ]$ ]]; then
    echo -n "   URL [http://localhost:11434]: "
    read -r OLLAMA_URL
    OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
    COMPOSE_PROFILES=""
    LOCAL_OLLAMA=false
    echo -e "   ${GREEN}✓${NC} Using external Ollama: $OLLAMA_URL\n"
  else
    OLLAMA_URL="http://ollama:11434"
    COMPOSE_PROFILES="local-ollama"
    LOCAL_OLLAMA=true
    echo -e "   ${GREEN}✓${NC} Local Ollama will be started\n"
  fi

  # 3. Access mode
  echo -n "🌐 Publish API on the host (127.0.0.1:8484)? [Y/n] "
  read -r PUBLISH_HOST

  if [[ "$PUBLISH_HOST" =~ ^[nN]$ ]]; then
    ACCESS_MODE="internal"
    HOST_BIND_ADDRESS="127.0.0.1"
    HOST_PORT="8484"
    PUBLIC_URL="http://rag-api:8080"

    echo -n "🔐 Require bearer token for internal-only mode? [y/N] "
    read -r REQUIRE_AUTH
    if [[ "$REQUIRE_AUTH" =~ ^[yYjJ]$ ]]; then
      AUTH_REQUIRED="true"
      generated_token="$(openssl rand -hex 32)"
      echo -e "   ${GREEN}✓${NC} Internal-only mode with bearer token\n"
    else
      AUTH_REQUIRED="false"
      generated_token=""
      echo -e "   ${GREEN}✓${NC} Internal-only mode, no authentication (trusted network)\n"
    fi
  else
    ACCESS_MODE="host"
    HOST_BIND_ADDRESS="127.0.0.1"
    HOST_PORT="8484"
    PUBLIC_URL="http://localhost:8484"

    echo -n "🔐 Require bearer token? [Y/n] "
    read -r REQUIRE_AUTH
    if [[ "$REQUIRE_AUTH" =~ ^[nN]$ ]]; then
      AUTH_REQUIRED="false"
      generated_token=""
      echo -e "   ${YELLOW}⚠️  Authentication disabled – API is open to anyone who can reach port ${HOST_PORT}.${NC}"
      echo -e "   ${YELLOW}   Only use this for local testing.${NC}\n"
    else
      AUTH_REQUIRED="true"
      generated_token="$(openssl rand -hex 32)"
      echo -e "   ${GREEN}✓${NC} Host access enabled at http://${HOST_BIND_ADDRESS}:${HOST_PORT}\n"
    fi
  fi

  # 4. Write .env
  cat > .env <<EOF
VAULT_PATH=$VAULT_PATH
OLLAMA_URL=$OLLAMA_URL
COMPOSE_PROFILES=$COMPOSE_PROFILES
ACCESS_MODE=$ACCESS_MODE
HOST_BIND_ADDRESS=$HOST_BIND_ADDRESS
HOST_PORT=$HOST_PORT
PUBLIC_URL=$PUBLIC_URL
AUTH_REQUIRED=$AUTH_REQUIRED
API_BEARER_TOKEN=$generated_token
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
  if [[ -n "$EXISTING_VAULT" && -d "$EXISTING_VAULT" ]]; then
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
      set -a; source .env; set +a
      ACCESS_MODE="${ACCESS_MODE:-host}"
      HOST_BIND_ADDRESS="${HOST_BIND_ADDRESS:-127.0.0.1}"
      HOST_PORT="${HOST_PORT:-8484}"
      if [[ "$ACCESS_MODE" == "host" ]]; then
        PUBLIC_URL="${PUBLIC_URL:-http://${HOST_BIND_ADDRESS}:${HOST_PORT}}"
        AUTH_REQUIRED="${AUTH_REQUIRED:-true}"
      else
        PUBLIC_URL="${PUBLIC_URL:-http://rag-api:8080}"
        AUTH_REQUIRED="${AUTH_REQUIRED:-false}"
      fi
      if [[ "${AUTH_REQUIRED:-true}" == "true" && -z "${API_BEARER_TOKEN:-}" ]]; then
        API_BEARER_TOKEN="$(openssl rand -hex 32)"
        {
          echo ""
          echo "ACCESS_MODE=$ACCESS_MODE"
          echo "HOST_BIND_ADDRESS=$HOST_BIND_ADDRESS"
          echo "HOST_PORT=$HOST_PORT"
          echo "PUBLIC_URL=$PUBLIC_URL"
          echo "AUTH_REQUIRED=$AUTH_REQUIRED"
          echo "API_BEARER_TOKEN=$API_BEARER_TOKEN"
        } >> .env
        echo -e "${YELLOW}⚠️  Existing .env had no API token. A new token was added.${NC}"
        echo -e "   ${BOLD}${API_BEARER_TOKEN}${NC}\n"
      fi
      if [[ "${COMPOSE_PROFILES:-}" == *"local-ollama"* ]]; then
        LOCAL_OLLAMA=true
      else
        LOCAL_OLLAMA=false
      fi
      echo -e "${GREEN}✅ Using existing .env${NC}\n"
    fi
  else
    # .env exists but vault path is missing or invalid → run setup
    _run_setup
  fi
else
  _run_setup
fi


# Ensure the Docker network exists before starting containers.
# This is a no-op if the network already exists (e.g. created by n8n).
docker network create "${DOCKER_NETWORK:-rag-network}" > /dev/null 2>&1 || true

# ── Start Ollama & pull model (local only) ────────────────────────────────
if [[ "$LOCAL_OLLAMA" == true ]]; then
  echo "🦙 Starting Ollama container..."
  _compose --profile local-ollama up -d ollama

  echo "⏳ Waiting for Ollama API..."
  attempts=0
  until docker exec ollama ollama list > /dev/null 2>&1; do
    sleep 2
    attempts=$(( attempts + 1 ))
    [ "$attempts" -ge 60 ] && die "Ollama did not respond after 2 minutes. Check: docker logs ollama"
  done

  echo "📥 Pulling nomic-embed-text (first run: ~1 min)..."
  docker exec ollama ollama pull nomic-embed-text
  echo -e "${GREEN}✅ Model ready${NC}\n"
fi

# ── Start rag-api ─────────────────────────────────────────────────────────
echo "🐳 Building and starting rag-api..."
_compose up -d --build rag-api || die "docker compose failed. Check: docker logs rag-api"
echo ""

# ── Wait for indexing (Ctrl+C skips, containers keep running) ────────────
trap 'printf "\n\n"; echo -e "${YELLOW}⏳ Indexing continues in the background.${NC}"; _summary; exit 0' INT

echo -e "${YELLOW}⏳ Waiting for indexing...${NC} ${BOLD}(Ctrl+C to skip)${NC}"

until _api_get /health > /dev/null 2>&1; do
  printf '\r\033[K   Starting API...'
  sleep 2
done

INDEXED=0
while true; do
  STATUS=$(_api_get /status 2>/dev/null || echo "{}")
  INDEXED=$(_json_int "$STATUS" "indexed_files")
  TOTAL=$(_json_int  "$STATUS" "total_files")

  if echo "$STATUS" | grep -q '"indexing":false'; then
    printf '\r\033[K'
    echo -e "${GREEN}✅ RAG API ready! ${INDEXED} files indexed.${NC}"
    break
  fi

  _draw_bar "$INDEXED" "$TOTAL"
  sleep 2
done

trap - INT

echo ""
_summary
echo ""

command -v osascript > /dev/null 2>&1 && \
  osascript -e "display notification \"${INDEXED} files indexed\" with title \"RAG API ready\" sound name \"Glass\"" 2>/dev/null &

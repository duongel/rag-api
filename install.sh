#!/usr/bin/env bash
# RAG API – One-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
set -euo pipefail

# Allow interactive input even when piped through curl | bash
exec < /dev/tty

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

REPO="duongel/rag-api"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/master"
INSTALL_DIR="${INSTALL_DIR:-$HOME/rag-api}"

info()  { echo -e "${GREEN}✅  $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️   $*${NC}"; }
die()   { echo -e "${RED}❌  $*${NC}" >&2; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        RAG API  –  Installer         ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────────
echo "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker and try again."
docker info >/dev/null 2>&1       || die "Docker is not running. Start Docker and try again."
info "Docker is ready"
echo ""

# ── Install directory ─────────────────────────────────────────────────────
echo -e "Install directory: ${BOLD}${INSTALL_DIR}${NC}"
read -r -p "Use this directory? [Y/n] " _CONFIRM; _CONFIRM="${_CONFIRM:-Y}"
if [[ "$_CONFIRM" =~ ^[Nn] ]]; then
  read -r -p "Enter install directory: " INSTALL_DIR
  INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
fi
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
echo ""

# ── Configuration ─────────────────────────────────────────────────────────
echo -e "${BOLD}Configuration${NC}"
echo "──────────────────────────────────────"

# Data sources
echo "Data sources:"
echo "  1) all       – Obsidian + Paperless"
echo "  2) obsidian  – Obsidian vault only"
echo "  3) paperless – Paperless-NGX only"
read -r -p "Choice [1]: " _DS; _DS="${_DS:-1}"
case "$_DS" in
  2) DATA_SOURCES="obsidian"  ;;
  3) DATA_SOURCES="paperless" ;;
  *) DATA_SOURCES="all"       ;;
esac

# Vault path
VAULT_PATH=""
if [[ "$DATA_SOURCES" != "paperless" ]]; then
  while [[ -z "$VAULT_PATH" || ! -d "$VAULT_PATH" ]]; do
    read -r -p "Obsidian vault path (absolute path): " VAULT_PATH
    VAULT_PATH="${VAULT_PATH/#\~/$HOME}"
    [[ -d "$VAULT_PATH" ]] || warn "Directory not found, try again."
  done
fi

# Ollama URL
read -r -p "Ollama URL [http://host.docker.internal:11434]: " OLLAMA_URL
OLLAMA_URL="${OLLAMA_URL:-http://host.docker.internal:11434}"

# Bearer token
if command -v openssl >/dev/null 2>&1; then
  _GENERATED=$(openssl rand -hex 32)
  read -r -p "API Bearer Token [auto-generate]: " API_BEARER_TOKEN
  API_BEARER_TOKEN="${API_BEARER_TOKEN:-$_GENERATED}"
else
  API_BEARER_TOKEN=""
  while [[ -z "$API_BEARER_TOKEN" ]]; do
    read -r -p "API Bearer Token (required, choose a long random string): " API_BEARER_TOKEN
  done
fi

# Port
read -r -p "Host port [8484]: " HOST_PORT
HOST_PORT="${HOST_PORT:-8484}"

# Paperless (optional)
PAPERLESS_URL=""; PAPERLESS_TOKEN=""
if [[ "$DATA_SOURCES" != "obsidian" ]]; then
  read -r -p "Paperless URL (optional, press Enter to skip): " PAPERLESS_URL
  if [[ -n "$PAPERLESS_URL" ]]; then
    read -r -p "Paperless API token: " PAPERLESS_TOKEN
  fi
fi
echo ""

# ── Download compose files ────────────────────────────────────────────────
echo "Downloading configuration files..."
curl -fsSL "${RAW_BASE}/docker-compose.dist.yml" -o docker-compose.yml
curl -fsSL "${RAW_BASE}/docker-compose.host.yml" -o docker-compose.host.yml
info "Files downloaded"

# ── Write .env ────────────────────────────────────────────────────────────
cat > .env <<EOF
DATA_SOURCES=${DATA_SOURCES}
VAULT_PATH=${VAULT_PATH}
OLLAMA_URL=${OLLAMA_URL}
EMBED_MODEL=nomic-embed-text
PUBLIC_URL=http://localhost:${HOST_PORT}
AUTH_REQUIRED=true
API_BEARER_TOKEN=${API_BEARER_TOKEN}
ACCESS_MODE=host
HOST_BIND_ADDRESS=127.0.0.1
HOST_PORT=${HOST_PORT}
EOF
[[ -n "$PAPERLESS_URL"   ]] && echo "PAPERLESS_URL=${PAPERLESS_URL}"     >> .env
[[ -n "$PAPERLESS_TOKEN" ]] && echo "PAPERLESS_TOKEN=${PAPERLESS_TOKEN}" >> .env
info ".env written"

# ── Docker network ────────────────────────────────────────────────────────
if ! docker network inspect rag-network >/dev/null 2>&1; then
  docker network create rag-network >/dev/null
  info "Docker network 'rag-network' created"
fi

# ── Pull & start ──────────────────────────────────────────────────────────
echo "Pulling image (first run may take a few minutes)..."
docker compose -f docker-compose.yml -f docker-compose.host.yml pull rag-api
echo "Starting RAG API..."
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d rag-api
echo ""

# ── Done ──────────────────────────────────────────────────────────────────
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║    RAG API is up and running! 🚀     ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  URL:     ${BLUE}http://127.0.0.1:${HOST_PORT}${NC}"
echo -e "  Token:   ${BOLD}${API_BEARER_TOKEN}${NC}"
echo ""
echo -e "  Logs:    ${BOLD}docker logs -f rag-api${NC}"
echo -e "  Stop:    ${BOLD}cd ${INSTALL_DIR} && docker compose -f docker-compose.yml -f docker-compose.host.yml down${NC}"
echo -e "  Update:  ${BOLD}cd ${INSTALL_DIR} && docker compose pull && docker compose up -d${NC}"
echo ""

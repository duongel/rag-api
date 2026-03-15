#!/usr/bin/env bash
# RAG API – Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
set -euo pipefail

BASE="https://raw.githubusercontent.com/duongel/rag-api/master"
INSTALL_DIR="${INSTALL_DIR:-$HOME/rag-api}"

BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

command -v curl   >/dev/null 2>&1 || { echo -e "${RED}❌ curl is required but not installed.${NC}" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}❌ Docker not found.${NC}" >&2; exit 1; }
docker info       >/dev/null 2>&1 || { echo -e "${RED}❌ Docker is not running.${NC}" >&2; exit 1; }

# Re-attach stdin to the terminal so interactive prompts work when piped through bash
exec < /dev/tty

if [[ -d "$INSTALL_DIR" ]]; then
  if [[ -f "$INSTALL_DIR/start.sh" && -f "$INSTALL_DIR/docker-compose.yml" ]]; then
    echo -e "${BOLD}🔄 Updating existing installation in ${INSTALL_DIR}...${NC}"
  else
    echo -e "${RED}❌ Directory exists but doesn't look like a rag-api installation:${NC} ${INSTALL_DIR}" >&2
    echo -e "${YELLOW}   Refusing to overwrite unrelated files. Set INSTALL_DIR to another path.${NC}" >&2
    exit 1
  fi
else
  echo -e "${BOLD}📦 Installing RAG API into ${INSTALL_DIR}...${NC}"
  mkdir -p "$INSTALL_DIR"
fi

for f in \
  docker-compose.yml \
  docker-compose.host.yml \
  docker-compose.obsidian.yml \
  docker-compose.paperless.yml \
  start.sh
do
  curl -fsSL "$BASE/$f" -o "$INSTALL_DIR/$f"
done

chmod +x "$INSTALL_DIR/start.sh"
echo -e "${GREEN}✅ Files ready.${NC}"
echo ""
exec "$INSTALL_DIR/start.sh" "$@"

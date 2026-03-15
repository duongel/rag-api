#!/usr/bin/env bash
# RAG API – Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
set -euo pipefail

exec < /dev/tty

BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-$HOME/rag-api}"

command -v docker >/dev/null 2>&1 || { echo -e "${RED}❌ Docker not found.${NC}"; exit 1; }
docker info >/dev/null 2>&1       || { echo -e "${RED}❌ Docker is not running.${NC}"; exit 1; }
command -v git >/dev/null 2>&1    || { echo -e "${RED}❌ Git not found.${NC}"; exit 1; }

if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo -e "${BOLD}Updating existing installation in ${INSTALL_DIR}...${NC}"
  git -C "$INSTALL_DIR" pull --rebase
else
  echo -e "${BOLD}Cloning into ${INSTALL_DIR}...${NC}"
  git clone https://github.com/duongel/rag-api.git "$INSTALL_DIR"
fi

echo -e "${GREEN}✅ Ready${NC}"
exec "$INSTALL_DIR/start.sh" "$@"

#!/usr/bin/env bash
# RAG API – Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
set -euo pipefail

BASE="https://raw.githubusercontent.com/duongel/rag-api/master"
INSTALL_DIR="${INSTALL_DIR:-$HOME/rag-api}"

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

command -v curl   >/dev/null 2>&1 || { echo -e "${RED}❌ curl is required but not installed.${NC}" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}❌ Docker not found.${NC}" >&2; exit 1; }
docker info       >/dev/null 2>&1 || { echo -e "${RED}❌ Docker is not running.${NC}" >&2; exit 1; }

# When piped through bash (`curl … | bash`), stdin is the pipe.
# We must NOT `exec < /dev/tty` here because that would steal bash's
# script-reading source and cause the remainder of the script to hang.
# Instead we set a flag and redirect stdin only in the final `exec` call
# so start.sh (read from a file on disk) gets an interactive terminal.
_NEED_TTY_REDIRECT=false
if [[ ! -t 0 ]]; then
  if [[ -r /dev/tty ]]; then
    _NEED_TTY_REDIRECT=true
  else
    echo -e "${RED}❌ Interactive terminal required for setup, but no TTY is attached.${NC}" >&2
    echo -e "${YELLOW}   Run this inside an interactive SSH session, then execute:${NC}" >&2
    echo -e "   ${BOLD}curl -fsSL ${BASE}/install.sh | bash${NC}" >&2
    echo -e "${YELLOW}   If you connected with ssh, force a TTY with:${NC} ${BOLD}ssh -t <host>${NC}" >&2
    exit 1
  fi
fi

if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/start.sh" && -f "$INSTALL_DIR/docker-compose.yml" ]]; then
  echo -e "${BOLD}🔄 Updating existing installation in ${INSTALL_DIR}...${NC}"
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
if [[ "$_NEED_TTY_REDIRECT" == true ]]; then
  exec "$INSTALL_DIR/start.sh" "$@" < /dev/tty
else
  exec "$INSTALL_DIR/start.sh" "$@"
fi

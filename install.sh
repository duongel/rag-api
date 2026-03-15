#!/bin/bash
# RAG API – One-liner installer
# Usage: curl -fsSL https://raw.githubusercontent.com/duongel/rag-api/master/install.sh | bash
set -e

BASE="https://raw.githubusercontent.com/duongel/rag-api/master"
DIR="${RAG_API_DIR:-rag-api}"

command -v curl > /dev/null 2>&1 || { echo "❌ curl is required but not installed." >&2; exit 1; }
command -v docker > /dev/null 2>&1 || { echo "❌ docker is required but not installed." >&2; exit 1; }

echo "📦 Installing RAG API into ./$DIR"
mkdir -p "$DIR"

for f in \
  docker-compose.yml \
  docker-compose.host.yml \
  docker-compose.obsidian.yml \
  docker-compose.paperless.yml \
  start.sh
do
  curl -fsSL "$BASE/$f" -o "$DIR/$f"
done

chmod +x "$DIR/start.sh"
echo "✅ Files downloaded. Starting setup..."
echo ""
cd "$DIR" && bash start.sh

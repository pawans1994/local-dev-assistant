#!/usr/bin/env bash
set -e

REPO="${1:-.}"
REPO="$(cd "$REPO" && pwd)"

echo "Local Dev Assistant"
echo "Repo: $REPO"
echo ""

echo "Building semantic index..."
rm -f "$REPO/code_index.json"
python build_index.py --path "$REPO"

if [ $? -ne 0 ]; then
  echo "Indexing failed. Exiting."
  exit 1
fi

echo ""
python chat.py --repo "$REPO"

#!/usr/bin/env bash
# Deploy Moku to build-small-hackathon/moku-the-first-word
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPACE_REPO="https://huggingface.co/spaces/build-small-hackathon/moku-the-first-word"
CLONE_DIR="${TMPDIR:-/tmp}/moku-hf-space"

if [[ -z "${HF_TOKEN:-}" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    HF_TOKEN="$(grep '^HF_TOKEN=' "$ROOT/.env" | cut -d= -f2-)"
  fi
fi
if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "Set HF_TOKEN (write access to build-small-hackathon org Spaces)."
  exit 1
fi

rm -rf "$CLONE_DIR"
git clone "https://AravindMohan:${HF_TOKEN}@huggingface.co/spaces/build-small-hackathon/moku-the-first-word" "$CLONE_DIR"

rsync -a --delete \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.sqlite3' \
  --exclude '.DS_Store' \
  "$ROOT/" "$CLONE_DIR/"

cd "$CLONE_DIR"
git add -A
git diff --cached --quiet && { echo "Nothing to deploy."; exit 0; }
git commit -m "Deploy Moku: The First Word"
git push origin main

echo "Deployed: https://huggingface.co/spaces/build-small-hackathon/moku-the-first-word"

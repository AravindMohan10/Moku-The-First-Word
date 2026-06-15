#!/usr/bin/env bash
# Wait for Modal vLLM cold start (merged MiniCPM ~3-6 min). Run after: modal deploy modal/moku_modal.py
set -euo pipefail
BASE="${MOKU_MODEL_BASE_URL:-https://m-aravind619--moku-the-first-word-serve.modal.run/v1}"
BASE="${BASE%/}"
URL="${BASE}/models"

echo "Warming Modal: $URL"
echo "Cold start can take 3-6 minutes — do not stop early."

for i in $(seq 1 30); do
  if curl -sf --max-time 45 "$URL" >/dev/null 2>&1; then
    echo "Modal is warm (attempt $i)."
    curl -sf --max-time 10 "$URL" | python3 -c "import sys,json; d=json.load(sys.stdin); print('models:', [m['id'] for m in d.get('data',[])])"
    exit 0
  fi
  echo "attempt $i: still starting (0 bytes / timeout)..."
  sleep 15
done

echo "Modal did not respond in ~7.5 min. Check: modal app logs moku-the-first-word"
exit 1

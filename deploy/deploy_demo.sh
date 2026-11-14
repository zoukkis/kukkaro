#!/usr/bin/env bash
# Deploys (or updates) the public Kukkaro demo from your machine to a server you can SSH into.
#
#   bash deploy/deploy_demo.sh <public-hostname> [ssh-key]
#   e.g. bash deploy/deploy_demo.sh 95.133.254.73.compute.verda.run ~/.ssh/kukkaro_verda
#
# What it does:
#   1. builds the web app against the real API (VITE_USE_MOCK=false)
#   2. writes the server's .env from your root .env: only the keys the app needs, never HF_TOKEN
#   3. uploads both plus deploy/remote_setup.sh and runs it as root on the server
# Requirements: node/npm, ssh/scp, a root .env with the API keys, the server's SSH key.
set -euo pipefail
HOST="${1:?usage: deploy_demo.sh <public-hostname> [ssh-key]}"
KEY="${2:-$HOME/.ssh/kukkaro_verda}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

echo "== build web app"
# npm ci only when node_modules is missing: on Windows a running dev server locks node_modules.
(cd "$ROOT/web" && { [ -d node_modules ] || npm ci; } && VITE_USE_MOCK=false VITE_CUSTOMER_ID="${DEMO_CUSTOMER_ID:-CUST02979}" npm run build)
tar -czf "$TMP/web-dist.tgz" -C "$ROOT/web/dist" .

echo "== server .env (selected keys only)"
grep -E '^(LLM_PROVIDER|GEMINI_API_KEY|GEMINI_MODEL|GEMMA_MODEL|GEMMA_BASE_URL|GEMMA_API_KEY|EXA_API_KEY|DEMO_CUSTOMER_ID|DEMO_TODAY)=' "$ROOT/.env" > "$TMP/kukkaro.env"
echo "DATA_DIR=../data" >> "$TMP/kukkaro.env"
echo "   $(cut -d= -f1 "$TMP/kukkaro.env" | tr '\n' ' ')"

echo "== upload and set up"
tr -d '\r' < "$ROOT/deploy/remote_setup.sh" > "$TMP/remote_setup.sh"   # Windows checkouts may add CR
scp "${SSH_OPTS[@]}" -q "$TMP/web-dist.tgz" "$TMP/kukkaro.env" "$TMP/remote_setup.sh" "root@$HOST:/root/"
ssh "${SSH_OPTS[@]}" "root@$HOST" "bash /root/remote_setup.sh $HOST"

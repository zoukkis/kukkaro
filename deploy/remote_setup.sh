#!/usr/bin/env bash
# Runs ON the demo server (Ubuntu 24.04, e.g. a Verda CPU instance) as root. Idempotent: run it
# again to update to the latest main. Called by deploy/deploy_demo.sh; do not run it by hand
# unless /root/kukkaro.env and /root/web-dist.tgz have been uploaded.
#
#   bash remote_setup.sh <public-hostname>     e.g. 95.133.254.73.compute.verda.run
#
# Result: Caddy serves https://<public-hostname> (automatic Let's Encrypt certificate) and proxies
# to uvicorn on 127.0.0.1:8000, which serves both /api and the built web app.
set -euo pipefail
HOST="${1:?usage: remote_setup.sh <public-hostname>}"
APP=/opt/kukkaro
REPO=https://github.com/zoukkis/kukkaro.git
export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -q
apt-get install -y -q git curl ca-certificates python3-venv caddy >/dev/null

echo "== code (latest main)"
if [ -d "$APP/.git" ]; then git -C "$APP" fetch -q origin && git -C "$APP" reset -q --hard origin/main; else git clone -q "$REPO" "$APP"; fi
git -C "$APP" log --oneline -1

echo "== secrets (never committed; uploaded by deploy_demo.sh)"
install -m 600 /root/kukkaro.env "$APP/.env"

echo "== python"
[ -d "$APP/backend/.venv" ] || python3 -m venv "$APP/backend/.venv"
"$APP/backend/.venv/bin/pip" install -q --upgrade pip
"$APP/backend/.venv/bin/pip" install -q -e "$APP/backend"

echo "== data: S-Bank's synthetic dataset from its official source (not redistributed by us)"
if [ ! -f "$APP/data/processed/transactions.parquet" ]; then
  [ -s "$APP/data/raw/tx_junction_transactions.csv" ] || bash "$APP/scripts/get_data.sh"
  (cd "$APP/backend" && .venv/bin/python -m kukkaro.data.prepare)
fi

echo "== web app (built on the developer machine)"
rm -rf "$APP/web/dist" && mkdir -p "$APP/web/dist"
tar -xzf /root/web-dist.tgz -C "$APP/web/dist"
test -f "$APP/web/dist/index.html"

echo "== service"
cat > /etc/systemd/system/kukkaro.service <<EOF
[Unit]
Description=Kukkaro demo (FastAPI + web app)
After=network-online.target

[Service]
WorkingDirectory=$APP/backend
ExecStart=$APP/backend/.venv/bin/uvicorn kukkaro.api.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q kukkaro.service
systemctl restart kukkaro.service

echo "== https (Caddy, automatic certificate)"
cat > /etc/caddy/Caddyfile <<EOF
$HOST {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
EOF
systemctl restart caddy

echo "== waiting for the app (data load takes a few seconds)"
for i in $(seq 1 60); do
  if curl -fs http://127.0.0.1:8000/api/health >/dev/null; then curl -s http://127.0.0.1:8000/api/health; echo; break; fi
  sleep 2
done
echo "== done: https://$HOST"

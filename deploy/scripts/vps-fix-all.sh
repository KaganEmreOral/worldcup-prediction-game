#!/usr/bin/env bash
# One-shot VPS recovery: pull, docker on 3010/8010, fix nginx, verify ACME path.
# Run from repo: sudo bash deploy/scripts/vps-fix-all.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

echo "==> 1. Git pull (latest nginx + compose fixes)"
git pull || echo "WARN: git pull failed — continue with local files"

if [[ ! -f .env.production ]]; then
  cp .env.production.example .env.production
  echo "Created .env.production — EDIT SECRETS before production use!"
fi

grep -q '^FRONTEND_HOST_PORT=' .env.production || echo 'FRONTEND_HOST_PORT=3010' >> .env.production
grep -q '^BACKEND_HOST_PORT=' .env.production || echo 'BACKEND_HOST_PORT=8010' >> .env.production

echo "==> 2. Docker stack"
bash deploy/scripts/deploy-app.sh

echo "==> 3. Nginx"
sudo bash deploy/scripts/fix-nginx-on-server.sh

source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

echo "==> 4. Local checks"
curl -sf "http://127.0.0.1:${FRONTEND_HOST_PORT}/" >/dev/null && echo "OK frontend local" || echo "FAIL frontend"
curl -sf "http://127.0.0.1:${BACKEND_HOST_PORT:-8010}/api/health" && echo "OK backend local"

echo "==> 5. ACME webroot (via Host header)"
PROBE="probe-$$"
echo ok | sudo tee "/var/www/certbot/${PROBE}" >/dev/null
curl -sf -H "Host: worldcupytu.org" "http://127.0.0.1/.well-known/acme-challenge/${PROBE}" && echo "OK ACME local" || echo "FAIL ACME local — fix nginx first"
sudo rm -f "/var/www/certbot/${PROBE}"

echo ""
echo "==> 6. Public DNS must point to THIS server (not Namecheap forward)"
echo "    dig +short worldcupytu.org"
echo "    dig +short www.worldcupytu.org"
echo ""
echo "When both show your VPS IP and ACME works:"
echo "  sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh"

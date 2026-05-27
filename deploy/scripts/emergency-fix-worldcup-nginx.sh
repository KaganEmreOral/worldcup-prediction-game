#!/usr/bin/env bash
# Fix worldcupytu.org serving the WRONG site (maltamentor on :3000).
# Only touches the worldcup vhost — does NOT modify other Nginx sites.
# Run on VPS: sudo bash deploy/scripts/emergency-fix-worldcup-nginx.sh
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

SITE="/etc/nginx/sites-available/${DOMAIN}"
if [[ ! -f "$SITE" ]]; then
  echo "ERROR: ${SITE} not found. Run: sudo bash deploy/scripts/install-nginx-site.sh"
  exit 1
fi

echo "==> Fixing ${SITE} only (frontend → ${FRONTEND_HOST_PORT}, backend → ${BACKEND_HOST_PORT})"
echo "    Other vhosts (maltamentor.com etc.) are NOT modified."

cp "${SITE}" "${SITE}.bak.$(date +%Y%m%d%H%M%S)"

# Replace common wrong upstream ports inside worldcup config only
sed -i \
  -e "s|127.0.0.1:3000|127.0.0.1:${FRONTEND_HOST_PORT}|g" \
  -e "s|127.0.0.1:8000|127.0.0.1:${BACKEND_HOST_PORT}|g" \
  "$SITE"

if grep -q "127.0.0.1:3000" "$SITE" || grep -q "127.0.0.1:8000" "$SITE"; then
  echo "WARNING: config may still reference 3000/8000 — reinstall from repo:"
  echo "  sudo bash deploy/scripts/fix-nginx-on-server.sh"
  exit 1
fi

if ! grep -q "server_name.*${DOMAIN}" "$SITE"; then
  echo "ERROR: server_name for ${DOMAIN} missing in ${SITE}"
  exit 1
fi

nginx -t
systemctl reload nginx

echo ""
echo "OK: ${DOMAIN} → 127.0.0.1:${FRONTEND_HOST_PORT} (frontend), 127.0.0.1:${BACKEND_HOST_PORT} (api)"
echo "Verify:"
echo "  curl -sI -H 'Host: ${DOMAIN}' http://127.0.0.1/ | head -5"
echo "  curl -s http://127.0.0.1:${BACKEND_HOST_PORT}/api/health"

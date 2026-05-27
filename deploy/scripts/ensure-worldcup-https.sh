#!/usr/bin/env bash
# worldcupytu.org: HTTP works but HTTPS shows maltamentor → install SSL vhost for World Cup.
# Does NOT edit maltamentor.com config (except warns if it steals worldcup server_name).
# Run on VPS: sudo bash deploy/scripts/ensure-worldcup-https.sh
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SITE="/etc/nginx/sites-available/${DOMAIN}"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

echo "==> Checking for config conflicts"
CONFLICT=0
for f in /etc/nginx/sites-enabled/*; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  [[ "$base" == *"${DOMAIN}"* ]] && continue
  if grep -qE "server_name[^;]*${DOMAIN}" "$f" 2>/dev/null; then
    echo "CONFLICT: ${f} lists ${DOMAIN} in server_name (maltamentor steals HTTPS)."
    echo "  Edit that file and REMOVE ${DOMAIN} from server_name — only ${SITE} should have it."
    CONFLICT=1
  fi
done

if [[ "$CONFLICT" -eq 1 ]]; then
  echo ""
  echo "Fix the conflict above, then re-run this script."
  exit 1
fi

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  echo "ERROR: No SSL cert at /etc/letsencrypt/live/${DOMAIN}/"
  echo "  Run: sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh"
  exit 1
fi

if [[ -f "$SITE" ]] && grep -qE 'listen\s+443' "$SITE"; then
  echo "==> ${SITE} already has listen 443 — fixing ports only"
  cp "$SITE" "${SITE}.bak.$(date +%Y%m%d%H%M%S)"
  sed -i \
    -e "s|127.0.0.1:3000|127.0.0.1:${FRONTEND_HOST_PORT}|g" \
    -e "s|127.0.0.1:8000|127.0.0.1:${BACKEND_HOST_PORT}|g" \
    "$SITE"
else
  echo "==> Installing full HTTPS vhost (listen 443) → ports ${FRONTEND_HOST_PORT}/${BACKEND_HOST_PORT}"
  # shellcheck source=lib/acme-webroot.sh
  source "${REPO_ROOT}/deploy/scripts/lib/acme-webroot.sh"
  acme_ensure_dir
  cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy.conf" /etc/nginx/snippets/worldcup-proxy.conf
  cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy-ws.conf" /etc/nginx/snippets/worldcup-proxy-ws.conf
  cp "${REPO_ROOT}/deploy/nginx/conf.d/worldcup-limits.conf" /etc/nginx/conf.d/worldcup-limits.conf
  apply_ports_to_nginx_config \
    "${REPO_ROOT}/deploy/nginx/worldcupytu.org.conf" \
    "$SITE"
fi

ln -sf "$SITE" "/etc/nginx/sites-enabled/${DOMAIN}"

if grep -qE '127\.0\.0\.1:(3000|8000)\b' "$SITE"; then
  echo "ERROR: ${SITE} still uses 3000/8000"
  grep -n '127.0.0.1' "$SITE" || true
  exit 1
fi

if ! grep -qE 'listen\s+443' "$SITE"; then
  echo "ERROR: ${SITE} still has no listen 443 after install"
  exit 1
fi

nginx -t
systemctl reload nginx

echo ""
echo "==> Verify (must show World Cup, NOT maltamentor)"
if curl -sLk "https://${DOMAIN}/" | grep -qi 'world cup'; then
  echo "OK: https://${DOMAIN}/ serves World Cup"
else
  echo "FAIL: https://${DOMAIN}/ still wrong — run: sudo bash deploy/scripts/diagnose-nginx.sh"
  exit 1
fi

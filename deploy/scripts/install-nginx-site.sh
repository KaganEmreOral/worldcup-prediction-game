#!/usr/bin/env bash
# Install World Cup site into host Nginx WITHOUT touching other vhosts.
# Run from repo root on the VPS: sudo bash deploy/scripts/install-nginx-site.sh
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

echo "==> Installing Nginx snippets and rate limits (domain: ${DOMAIN})"
echo "    Upstream frontend: 127.0.0.1:${FRONTEND_HOST_PORT}"
echo "    Upstream backend:  127.0.0.1:${BACKEND_HOST_PORT}"
# shellcheck source=lib/acme-webroot.sh
source "${REPO_ROOT}/deploy/scripts/lib/acme-webroot.sh"
acme_ensure_dir

cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy.conf" /etc/nginx/snippets/worldcup-proxy.conf
cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy-ws.conf" /etc/nginx/snippets/worldcup-proxy-ws.conf
cp "${REPO_ROOT}/deploy/nginx/conf.d/worldcup-limits.conf" /etc/nginx/conf.d/worldcup-limits.conf

echo "==> Installing HTTP-only site config (Phase 1)"
apply_ports_to_nginx_config \
  "${REPO_ROOT}/deploy/nginx/worldcupytu.org.http-only.conf" \
  "/etc/nginx/sites-available/${DOMAIN}"
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"

echo "==> Testing Nginx configuration"
if grep -qE '127\.0\.0\.1:(3000|8000)\b' "/etc/nginx/sites-available/${DOMAIN}"; then
  echo "ERROR: ${DOMAIN} config still points at 3000/8000 (would show another site on this VPS)."
  echo "  Check .env.production: FRONTEND_HOST_PORT=3010 BACKEND_HOST_PORT=8010"
  exit 1
fi

nginx -t

echo "==> Reloading Nginx (existing sites unchanged)"
systemctl reload nginx

echo ""
echo "OK: ${DOMAIN} site enabled (HTTP only)."
echo "Next: sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh"

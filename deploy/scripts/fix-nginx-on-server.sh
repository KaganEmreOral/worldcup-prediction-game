#!/usr/bin/env bash
# Reinstall worldcupytu.org Nginx vhost from repo templates (fixes duplicate proxy_http_version).
# Run on VPS as root: sudo bash deploy/scripts/fix-nginx-on-server.sh
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

echo "==> Nginx upstream ports: frontend=${FRONTEND_HOST_PORT} backend=${BACKEND_HOST_PORT}"

# shellcheck source=lib/acme-webroot.sh
source "${REPO_ROOT}/deploy/scripts/lib/acme-webroot.sh"
acme_ensure_dir

cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy.conf" /etc/nginx/snippets/worldcup-proxy.conf
cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy-ws.conf" /etc/nginx/snippets/worldcup-proxy-ws.conf
cp "${REPO_ROOT}/deploy/nginx/conf.d/worldcup-limits.conf" /etc/nginx/conf.d/worldcup-limits.conf

# Pick HTTP-only unless SSL certs already exist
TEMPLATE="${REPO_ROOT}/deploy/nginx/worldcupytu.org.http-only.conf"
if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  TEMPLATE="${REPO_ROOT}/deploy/nginx/worldcupytu.org.conf"
  echo "==> Using HTTPS template (certificates found)"
else
  echo "==> Using HTTP-only template (no certificates yet)"
fi

apply_ports_to_nginx_config "$TEMPLATE" "/etc/nginx/sites-available/${DOMAIN}"
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"

nginx -t
systemctl reload nginx
echo "OK: ${DOMAIN} Nginx config reloaded"

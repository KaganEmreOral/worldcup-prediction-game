#!/usr/bin/env bash
# Obtain Let's Encrypt certificate and switch to HTTPS config.
# Prerequisites: HTTP site installed, nginx -t passes, port 80 serves ACME webroot.
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
EMAIL="${CERTBOT_EMAIL:?Set CERTBOT_EMAIL=your@email.com}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

if ! command -v certbot >/dev/null 2>&1; then
  echo "==> Installing certbot"
  apt-get update
  apt-get install -y certbot
fi

# shellcheck source=lib/acme-webroot.sh
source "${REPO_ROOT}/deploy/scripts/lib/acme-webroot.sh"
acme_ensure_dir

echo "==> Verifying Nginx config before certificate request"
if ! nginx -t; then
  echo "ERROR: nginx -t failed. Fix config first:"
  echo "  sudo bash deploy/scripts/install-nginx-site.sh"
  exit 1
fi
systemctl reload nginx

echo "==> Testing ACME webroot (port 80)"
acme_test_local "${DOMAIN}" || true
if ! acme_test_public "${DOMAIN}"; then
  echo "ERROR: ACME path not reachable publicly. Fix DNS (no Namecheap redirect) before certbot."
  echo "  See deploy/NAMECHEAP-DNS.md"
  exit 1
fi

echo "==> Requesting certificate for ${DOMAIN} and www.${DOMAIN}"
certbot certonly --webroot \
  -w /var/www/certbot \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive \
  --preferred-challenges http

echo "==> Installing HTTPS site config (Phase 2)"
cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy-ws.conf" /etc/nginx/snippets/worldcup-proxy-ws.conf
apply_ports_to_nginx_config \
  "${REPO_ROOT}/deploy/nginx/worldcupytu.org.conf" \
  "/etc/nginx/sites-available/${DOMAIN}"

nginx -t
systemctl reload nginx

echo "==> Enabling certbot auto-renewal timer"
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true

echo ""
echo "OK: HTTPS enabled for https://${DOMAIN}"
echo "Verify: curl -sI https://${DOMAIN}/api/health"

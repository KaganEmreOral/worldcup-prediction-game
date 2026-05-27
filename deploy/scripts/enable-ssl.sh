#!/usr/bin/env bash
# Obtain Let's Encrypt certificate and switch to HTTPS config.
# Prerequisites: DNS A records → this server, HTTP site already proxying.
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
EMAIL="${CERTBOT_EMAIL:?Set CERTBOT_EMAIL=your@email.com}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if ! command -v certbot >/dev/null 2>&1; then
  echo "==> Installing certbot"
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
fi

mkdir -p /var/www/certbot

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
cp "${REPO_ROOT}/deploy/nginx/worldcupytu.org.conf" "/etc/nginx/sites-available/${DOMAIN}"

nginx -t
systemctl reload nginx

echo "==> Enabling certbot auto-renewal timer"
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true

echo ""
echo "OK: HTTPS enabled for https://${DOMAIN}"
echo "Verify: curl -sI https://${DOMAIN}/api/health"

#!/usr/bin/env bash
# Install World Cup site into host Nginx WITHOUT touching other vhosts.
# Run from repo root on the VPS: sudo bash deploy/scripts/install-nginx-site.sh
set -euo pipefail

DOMAIN="${DOMAIN:-worldcupytu.org}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Installing Nginx snippets and rate limits (domain: ${DOMAIN})"
mkdir -p /var/www/certbot
chmod 755 /var/www/certbot

cp "${REPO_ROOT}/deploy/nginx/snippets/worldcup-proxy.conf" /etc/nginx/snippets/worldcup-proxy.conf
cp "${REPO_ROOT}/deploy/nginx/conf.d/worldcup-limits.conf" /etc/nginx/conf.d/worldcup-limits.conf

echo "==> Installing HTTP-only site config (Phase 1)"
cp "${REPO_ROOT}/deploy/nginx/worldcupytu.org.http-only.conf" "/etc/nginx/sites-available/${DOMAIN}"
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"

echo "==> Testing Nginx configuration"
nginx -t

echo "==> Reloading Nginx (existing sites unchanged)"
systemctl reload nginx

echo ""
echo "OK: ${DOMAIN} site enabled (HTTP only)."
echo "Next: ensure Docker app is on 127.0.0.1:3000 and :8000, then run:"
echo "  sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh"

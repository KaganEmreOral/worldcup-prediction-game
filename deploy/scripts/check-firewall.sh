#!/usr/bin/env bash
# Ensure HTTP/HTTPS are open; do not expose Docker app ports publicly.
set -euo pipefail

echo "==> Current UFW status"
ufw status verbose || true

echo ""
echo "==> Recommended rules (run manually if needed):"
echo "  sudo ufw allow OpenSSH"
echo "  sudo ufw allow 80/tcp"
echo "  sudo ufw allow 443/tcp"
echo "  sudo ufw enable"
echo ""
echo "Do NOT run: ufw allow 3000 or ufw allow 8000"
echo "Docker prod binds 127.0.0.1 only."

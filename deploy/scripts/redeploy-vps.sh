#!/usr/bin/env bash
# Full VPS redeploy in correct order (run from repo root).
# Usage: sudo bash deploy/scripts/redeploy-vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/scripts/redeploy-vps.sh"
  exit 1
fi

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"
load_host_ports "${REPO_ROOT}/.env.production"

echo "==> 1. Stop old containers"
docker compose -f docker-compose.prod.yml --env-file .env.production down 2>/dev/null || true

echo "==> 2. Start Docker (ports ${FRONTEND_HOST_PORT}/${BACKEND_HOST_PORT})"
sudo -u "${SUDO_USER:-root}" bash deploy/scripts/deploy-app.sh 2>/dev/null || bash deploy/scripts/deploy-app.sh

echo "==> 3. Install / refresh Nginx HTTP config"
bash deploy/scripts/install-nginx-site.sh

echo ""
echo "==> 4. When HTTP works, run SSL:"
echo "  CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh"

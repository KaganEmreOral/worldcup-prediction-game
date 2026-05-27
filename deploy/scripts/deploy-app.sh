#!/usr/bin/env bash
# Build and start production Docker stack (localhost ports only).
# Run from repo root: bash deploy/scripts/deploy-app.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production not found."
  echo "  cp .env.production.example .env.production"
  echo "  Edit secrets (SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD)."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed on this server."
  echo ""
  echo "Install Docker, then re-run this script:"
  echo "  sudo bash deploy/scripts/install-docker.sh"
  echo ""
  echo "Or manually: https://docs.docker.com/engine/install/ubuntu/"
  exit 1
fi

# Stop dev stack nginx if it was binding port 80 (does not affect host nginx)
if docker compose ps nginx 2>/dev/null | grep -q Up; then
  echo "==> Stopping dev docker-compose nginx (port 80 conflict)"
  docker compose stop nginx 2>/dev/null || true
fi

echo "==> Building and starting production containers"
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

echo "==> Waiting for healthchecks"
sleep 5
docker compose -f docker-compose.prod.yml ps

echo ""
echo "App should be reachable via host Nginx:"
echo "  Frontend: http://127.0.0.1:3000"
echo "  Backend:  http://127.0.0.1:8000/api/health"
echo ""
echo "If Nginx is configured: https://worldcupytu.org"

#!/usr/bin/env bash
# Build and start production Docker stack (localhost ports only).
# Run from repo root: bash deploy/scripts/deploy-app.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

# shellcheck source=lib/ports.sh
source "${REPO_ROOT}/deploy/scripts/lib/ports.sh"

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
  exit 1
fi

load_host_ports "${REPO_ROOT}/.env.production"

# Export for docker compose variable substitution (${FRONTEND_HOST_PORT} in compose file)
set -a
# shellcheck disable=SC1091
source "${REPO_ROOT}/.env.production"
set +a
export FRONTEND_HOST_PORT BACKEND_HOST_PORT

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.production)

check_port() {
  local port="$1" name="$2"
  if host_port_in_use "$port"; then
    echo "WARNING: port 127.0.0.1:${port} (${name}) is already in use."
    echo "  See what uses it:  sudo ss -tlnp | grep :${port}"
    echo "  Or:               sudo lsof -i :${port}"
    echo ""
    echo "  Fix options:"
    echo "    1) Stop the old process/container using this port"
    echo "    2) Use different ports in .env.production, then re-run Nginx install:"
    echo "       FRONTEND_HOST_PORT=3010"
    echo "       BACKEND_HOST_PORT=8010"
    echo "       sudo bash deploy/scripts/install-nginx-site.sh"
    return 1
  fi
  return 0
}

compose_stack_running() {
  local ids
  ids="$("${COMPOSE[@]}" ps -q 2>/dev/null || true)"
  [[ -n "$ids" ]]
}

PORT_OK=1
check_port "$FRONTEND_HOST_PORT" "frontend" || PORT_OK=0
check_port "$BACKEND_HOST_PORT" "backend" || PORT_OK=0

if [[ "$PORT_OK" -eq 0 ]]; then
  if compose_stack_running; then
    echo ""
    echo "==> Ports ${FRONTEND_HOST_PORT}/${BACKEND_HOST_PORT} are in use by this stack — redeploying in place (rebuild + restart)."
    "${COMPOSE[@]}" ps 2>/dev/null || true
  else
    echo ""
    echo "==> Port conflict — not owned by worldcup-prediction-game compose project:"
    "${COMPOSE[@]}" ps 2>/dev/null || true
    echo ""
    echo "Try: docker compose -f docker-compose.prod.yml --env-file .env.production down"
    echo "Or free the ports, then re-run this script."
    exit 1
  fi
fi

# Stop dev stack nginx if it was binding port 80
if docker compose ps nginx 2>/dev/null | grep -q Up; then
  echo "==> Stopping dev docker-compose nginx (port 80 conflict)"
  docker compose stop nginx 2>/dev/null || true
fi

echo "==> Published ports (must show 3010 / 8010, NOT 3000 / 8000):"
"${COMPOSE[@]}" config 2>/dev/null | grep -E "published:|FRONTEND|BACKEND" || true

echo "==> Building and starting production containers"
echo "    Frontend → 127.0.0.1:${FRONTEND_HOST_PORT}"
echo "    Backend  → 127.0.0.1:${BACKEND_HOST_PORT}"
"${COMPOSE[@]}" up -d --build

echo "==> Waiting for healthchecks"
sleep 5
"${COMPOSE[@]}" ps

echo ""
echo "App should be reachable via host Nginx:"
echo "  Frontend: http://127.0.0.1:${FRONTEND_HOST_PORT}"
echo "  Backend:  http://127.0.0.1:${BACKEND_HOST_PORT}/api/health"
echo ""
echo "If Nginx is configured: https://worldcupytu.org"

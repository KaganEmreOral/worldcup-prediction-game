# shellcheck shell=bash
# Load FRONTEND_HOST_PORT / BACKEND_HOST_PORT from repo .env.production

load_host_ports() {
  # Defaults 3010/8010 avoid clash with other Node apps on the same VPS (port 3000)
  FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-3010}"
  BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-8010}"
  local env_file="${1:-.env.production}"
  if [[ -f "$env_file" ]]; then
    local fe be
    fe="$(grep -E '^FRONTEND_HOST_PORT=' "$env_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    be="$(grep -E '^BACKEND_HOST_PORT=' "$env_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    [[ -n "$fe" ]] && FRONTEND_HOST_PORT="$fe"
    [[ -n "$be" ]] && BACKEND_HOST_PORT="$be"
  fi
}

host_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -qE ":${port}\b"
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1
    return $?
  fi
  return 1
}

apply_ports_to_nginx_config() {
  local src="$1" dest="$2"
  sed -e "s/127.0.0.1:3000/127.0.0.1:${FRONTEND_HOST_PORT}/g" \
      -e "s/127.0.0.1:8000/127.0.0.1:${BACKEND_HOST_PORT}/g" \
      "$src" >"$dest"
}

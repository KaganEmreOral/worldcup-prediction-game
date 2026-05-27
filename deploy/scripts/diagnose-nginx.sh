#!/usr/bin/env bash
# Show which ports each vhost uses (run on VPS, no changes).
set -uo pipefail

echo "==> DNS (if dig installed)"
command -v dig >/dev/null && dig +short worldcupytu.org A www.worldcupytu.org A maltamentor.com A || true

echo ""
echo "==> Listening ports (3000/3010/8000/8010)"
ss -tlnp 2>/dev/null | grep -E ':3000|:3010|:8000|:8010' || netstat -tlnp 2>/dev/null | grep -E ':3000|:3010|:8000|:8010' || true

echo ""
echo "==> Nginx enabled sites (server_name + upstream ports)"
for f in /etc/nginx/sites-enabled/*; do
  [[ -e "$f" ]] || continue
  echo "--- $f ---"
  grep -E 'listen |server_name |127\.0\.0\.1:(3000|3010|8000|8010)|upstream ' "$f" 2>/dev/null || true
done

echo ""
echo "==> What each URL serves (from this server)"
check() {
  local label="$1"
  shift
  local body
  body="$(curl -sLk --connect-timeout 5 "$@" 2>/dev/null | head -c 8000)" || body=""
  if echo "$body" | grep -qi 'maltamentor'; then
    echo "${label}: MALTAMENTOR (wrong for worldcup)"
  elif echo "$body" | grep -qi 'world cup'; then
    echo "${label}: World Cup OK"
  else
    echo "${label}: unknown"
  fi
}
check "http://worldcupytu.org" "http://worldcupytu.org/"
check "https://worldcupytu.org" "https://worldcupytu.org/"
check "https://www.worldcupytu.org" "https://www.worldcupytu.org/"

#!/usr/bin/env bash
# Fix worldcupytu.org serving maltamentor (wrong ports on HTTP and/or HTTPS).
# Reinstalls worldcup vhost from repo — does NOT touch maltamentor.com config.
# Run on VPS: sudo bash deploy/scripts/emergency-fix-worldcup-nginx.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

echo "==> Diagnosis (before fix)"
bash "${REPO_ROOT}/deploy/scripts/diagnose-nginx.sh" || true

echo ""
echo "==> Installing HTTPS vhost if missing, then fixing ports"
exec bash "${REPO_ROOT}/deploy/scripts/ensure-worldcup-https.sh"

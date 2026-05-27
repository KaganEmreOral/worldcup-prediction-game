# shellcheck shell=bash
# Certbot webroot: files must live under .well-known/acme-challenge/

ACME_WEBROOT="${ACME_WEBROOT:-/var/www/certbot}"
ACME_CHALLENGE_DIR="${ACME_WEBROOT}/.well-known/acme-challenge"

acme_ensure_dir() {
  mkdir -p "${ACME_CHALLENGE_DIR}"
  chmod 755 "${ACME_WEBROOT}" "${ACME_WEBROOT}/.well-known" "${ACME_CHALLENGE_DIR}" 2>/dev/null || true
}

acme_write_probe() {
  local name="$1"
  acme_ensure_dir
  echo ok >"${ACME_CHALLENGE_DIR}/${name}"
}

acme_remove_probe() {
  rm -f "${ACME_CHALLENGE_DIR}/$1"
}

acme_test_local() {
  local host="${1:-worldcupytu.org}"
  local name="probe-$(date +%s)"
  acme_write_probe "$name"
  if curl -sf -H "Host: ${host}" "http://127.0.0.1/.well-known/acme-challenge/${name}" | grep -q ok; then
    echo "OK ACME local (${host})"
    acme_remove_probe "$name"
    return 0
  fi
  echo "FAIL ACME local — check: ls -la ${ACME_CHALLENGE_DIR}"
  acme_remove_probe "$name"
  return 1
}

acme_test_public() {
  local domain="${1:-worldcupytu.org}"
  local name="probe-$(date +%s)"
  acme_write_probe "$name"
  if curl -sf "http://${domain}/.well-known/acme-challenge/${name}" | grep -q ok; then
    echo "OK ACME public (${domain})"
    acme_remove_probe "$name"
    return 0
  fi
  echo "FAIL ACME public (${domain}) — DNS or Namecheap redirect?"
  acme_remove_probe "$name"
  return 1
}

#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export KUBECONFIG="${PROJECT_DIR}/.local/vault-watchdogs-lab.kubeconfig"
VAULT_NS="vault"
WATCHDOG_NS="vault-watchdogs"
VAULT_STS="vault"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fail() { log "FAIL: $*"; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

wait_pods_ready() {
  for pod in vault-0 vault-1 vault-2; do
    kubectl -n "${VAULT_NS}" wait --for=condition=Ready "pod/${pod}" --timeout=180s >/dev/null
  done
  kubectl -n "${WATCHDOG_NS}" rollout status deployment/vault-watchdogs --timeout=180s >/dev/null
}

vault_token() { sed -n 's/^VAULT_ROOT_TOKEN=//p' "${PROJECT_DIR}/.env"; }

vault_exec() {
  local pod="$1"; shift
  kubectl -n "${VAULT_NS}" exec "${pod}" -- env VAULT_ADDR=http://127.0.0.1:8200 "$@"
}

vault_status_json() {
  vault_exec "$1" vault status -format=json 2>/dev/null || true
}

vault_leader() {
  for pod in vault-0 vault-1 vault-2; do
    if [[ "$(vault_status_json "${pod}" | jq -r '.active_time // empty')" != "0001-01-01T00:00:00Z" && \
          "$(vault_status_json "${pod}" | jq -r '.active_time // empty')" != "" ]]; then
      printf '%s\n' "${pod}"
      return 0
    fi
  done
  return 1
}

assert_all_vault_ready() {
  local count
  count="$(kubectl -n "${VAULT_NS}" get pods -l app.kubernetes.io/name=vault \
    -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -c '^true$' || true)"
  [[ "${count}" -eq 3 ]] || fail "expected 3 ready Vault pods, got ${count}"
}

assert_pvc_exists() {
  kubectl -n "${VAULT_NS}" get pvc "$1" >/dev/null || fail "PVC missing: $1"
}

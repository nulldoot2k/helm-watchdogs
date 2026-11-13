#!/usr/bin/env bash
set -Eeuo pipefail
TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/lib/common.sh
source "${TEST_DIR}/lib/common.sh"

need_cmd kubectl
need_cmd jq

TESTS_PASSED=0
TESTS_FAILED=0

run_case() {
  local name="$1"; shift
  log "CASE ${name}"
  if "$@"; then
    log "PASS ${name}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    log "FAIL ${name}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

case_healthy() {
  wait_pods_ready
  assert_all_vault_ready
  kubectl -n "${WATCHDOG_NS}" get lease vault-watchdogs-leader >/dev/null
}

case_seal_and_auto_unseal() {
  local leader
  leader="$(vault_leader)" || fail "could not find Vault leader"
  timeout 20s kubectl -n "${VAULT_NS}" exec "${leader}" -- \
    env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN="$(vault_token)" vault operator seal >/dev/null
  for _ in $(seq 1 30); do
    if kubectl -n "${VAULT_NS}" wait --for=condition=Ready pod/vault-0 pod/vault-1 pod/vault-2 --timeout=5s >/dev/null 2>&1 && \
       assert_all_vault_ready 2>/dev/null; then
      local current_leader
      current_leader="$(vault_leader || true)"
      [[ -n "${current_leader}" ]] && [[ "$(vault_status_json "${current_leader}" | jq -r '.sealed // true')" == "false" ]] && return 0
    fi
    sleep 2
  done
  fail "watchdog did not auto-unseal vault-0"
}

case_restart_preserves_pvc() {
  local pvc="data-vault-1"
  assert_pvc_exists "${pvc}"
  local before
  before="$(kubectl -n "${VAULT_NS}" get pvc "${pvc}" -o jsonpath='{.spec.volumeName}')"
  kubectl -n "${VAULT_NS}" delete pod vault-1 --wait=true >/dev/null
  kubectl -n "${VAULT_NS}" wait --for=condition=Ready pod/vault-1 --timeout=180s >/dev/null
  local after
  after="$(kubectl -n "${VAULT_NS}" get pvc "${pvc}" -o jsonpath='{.spec.volumeName}')"
  [[ "${before}" == "${after}" ]] || fail "PVC volume changed during pod restart"
  assert_pvc_exists "${pvc}"
}

case_delete_pod_keeps_all_pvc() {
  local before after
  before="$(kubectl -n "${VAULT_NS}" get pvc -o jsonpath='{range .items[*]}{.metadata.name}:{.spec.volumeName}{"\n"}{end}' | sort)"
  kubectl -n "${VAULT_NS}" delete pod vault-2 --wait=true >/dev/null
  kubectl -n "${VAULT_NS}" wait --for=condition=Ready pod/vault-2 --timeout=180s >/dev/null
  after="$(kubectl -n "${VAULT_NS}" get pvc -o jsonpath='{range .items[*]}{.metadata.name}:{.spec.volumeName}{"\n"}{end}' | sort)"
  [[ "${before}" == "${after}" ]] || fail "PVC inventory changed after pod deletion"
}

case_watchdog_restart() {
  kubectl -n "${WATCHDOG_NS}" rollout restart deployment/vault-watchdogs >/dev/null
  kubectl -n "${WATCHDOG_NS}" rollout status deployment/vault-watchdogs --timeout=180s >/dev/null
  kubectl -n "${WATCHDOG_NS}" get lease vault-watchdogs-leader >/dev/null
}

case_quorum_safety() {
  local replicas
  replicas="$(kubectl -n "${VAULT_NS}" get statefulset "${VAULT_STS}" -o jsonpath='{.spec.replicas}')"
  [[ "${replicas}" -ge 3 ]] || fail "quorum safety test requires at least 3 Vault replicas"
  log "quorum safety assertion: destructive remediation must remain disabled"
  kubectl -n "${WATCHDOG_NS}" get deployment vault-watchdogs \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="ALLOW_POD_DELETE")].value}' | grep -qx false \
    || fail "ALLOW_POD_DELETE is not false"
}

run_case healthy case_healthy
run_case seal_and_auto_unseal case_seal_and_auto_unseal
run_case restart_preserves_pvc case_restart_preserves_pvc
run_case delete_pod_keeps_all_pvc case_delete_pod_keeps_all_pvc
run_case watchdog_restart case_watchdog_restart
run_case quorum_safety case_quorum_safety

log "RESULT passed=${TESTS_PASSED} failed=${TESTS_FAILED}"
[[ "${TESTS_FAILED}" -eq 0 ]]

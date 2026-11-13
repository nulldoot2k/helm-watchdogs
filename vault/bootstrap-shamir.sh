#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
KUBECONFIG_FILE="${PROJECT_DIR}/.local/vault-watchdogs-lab.kubeconfig"
ENV_FILE="${PROJECT_DIR}/.env"
NAMESPACE="vault"
POD="vault-0"
VAULT_ADDR="http://127.0.0.1:8200"

export KUBECONFIG="${KUBECONFIG_FILE}"
umask 077

command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required" >&2; exit 1; }
test -f "${KUBECONFIG_FILE}" || { echo "Kind kubeconfig not found: ${KUBECONFIG_FILE}" >&2; exit 1; }

status_json="$(kubectl -n "${NAMESPACE}" exec "${POD}" -- \
  env VAULT_ADDR="${VAULT_ADDR}" vault status -format=json 2>/dev/null || true)"

if printf '%s' "${status_json}" | jq -e '.initialized == true' >/dev/null 2>&1; then
  test -f "${ENV_FILE}" || {
    echo "Vault is already initialized but ${ENV_FILE} is missing" >&2
    exit 1
  }
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  echo "Initializing Vault with 5 Shamir shares and threshold 3"
  init_json="$(kubectl -n "${NAMESPACE}" exec "${POD}" -- \
    env VAULT_ADDR="${VAULT_ADDR}" vault operator init \
      -key-shares=5 -key-threshold=3 -format=json)"

  key1="$(printf '%s' "${init_json}" | jq -r '.unseal_keys_b64[0]')"
  key2="$(printf '%s' "${init_json}" | jq -r '.unseal_keys_b64[1]')"
  key3="$(printf '%s' "${init_json}" | jq -r '.unseal_keys_b64[2]')"
  root_token="$(printf '%s' "${init_json}" | jq -r '.root_token')"

  test -n "${key1}" && test "${key1}" != null
  test -n "${key2}" && test "${key2}" != null
  test -n "${key3}" && test "${key3}" != null
  test -n "${root_token}" && test "${root_token}" != null

  {
    printf 'VAULT_ADDR=%q\n' "http://vault.test"
    printf 'VAULT_NAMESPACE=%q\n' "${NAMESPACE}"
    printf 'VAULT_ROOT_TOKEN=%q\n' "${root_token}"
    printf 'VAULT_UNSEAL_KEY_1=%q\n' "${key1}"
    printf 'VAULT_UNSEAL_KEY_2=%q\n' "${key2}"
    printf 'VAULT_UNSEAL_KEY_3=%q\n' "${key3}"
    printf 'VAULT_UNSEAL_THRESHOLD=%q\n' "3"
  } > "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
fi

# Keep the unseal loop independent from whether credentials were freshly
# generated or loaded from the existing .env file.
VAULT_UNSEAL_KEY_1="${VAULT_UNSEAL_KEY_1:-${key1:-}}"
VAULT_UNSEAL_KEY_2="${VAULT_UNSEAL_KEY_2:-${key2:-}}"
VAULT_UNSEAL_KEY_3="${VAULT_UNSEAL_KEY_3:-${key3:-}}"
test -n "${VAULT_UNSEAL_KEY_1}" && test -n "${VAULT_UNSEAL_KEY_2}" && test -n "${VAULT_UNSEAL_KEY_3}"
test -n "${VAULT_ROOT_TOKEN}"
# Commands run inside the pod must use Vault's local listener. The public
# hostname is intentionally stored in .env for clients outside the pod.
VAULT_ADDR="http://127.0.0.1:8200"

for pod in vault-0 vault-1 vault-2; do
  pod_status="$(kubectl -n "${NAMESPACE}" exec "${pod}" -- \
    env VAULT_ADDR="${VAULT_ADDR}" vault status -format=json 2>/dev/null || true)"
  if ! printf '%s' "${pod_status}" | jq -e '.initialized == true' >/dev/null 2>&1; then
    echo "${pod} is not initialized yet, skipping unseal"
    continue
  fi
  echo "Unsealing ${pod}"
  for key_name in VAULT_UNSEAL_KEY_1 VAULT_UNSEAL_KEY_2 VAULT_UNSEAL_KEY_3; do
    key_value="${!key_name}"
    kubectl -n "${NAMESPACE}" exec "${pod}" -- \
      env VAULT_ADDR="${VAULT_ADDR}" vault operator unseal "${key_value}" >/dev/null
  done
done

echo "Vault status"
kubectl -n "${NAMESPACE}" exec vault-0 -- \
  env VAULT_ADDR="${VAULT_ADDR}" VAULT_TOKEN="${VAULT_ROOT_TOKEN}" vault status
echo "Credentials saved to ${ENV_FILE} with mode 600"

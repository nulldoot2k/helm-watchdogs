#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBECONFIG="${PROJECT_DIR}/.local/vault-watchdogs-lab.kubeconfig"
NAMESPACE="vault-watchdogs"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret generic vault-watchdogs-credentials \
  --from-literal=VAULT_UNSEAL_KEY_1="$(sed -n 's/^VAULT_UNSEAL_KEY_1=//p' "${PROJECT_DIR}/.env")" \
  --from-literal=VAULT_UNSEAL_KEY_2="$(sed -n 's/^VAULT_UNSEAL_KEY_2=//p' "${PROJECT_DIR}/.env")" \
  --from-literal=VAULT_UNSEAL_KEY_3="$(sed -n 's/^VAULT_UNSEAL_KEY_3=//p' "${PROJECT_DIR}/.env")" \
  --dry-run=client -o yaml | kubectl apply -f -
kind load docker-image vault-watchdogs:dev --name vault-watchdogs-lab
helm upgrade --install vault-watchdogs "${PROJECT_DIR}/charts/vault-watchdogs" \
  --namespace "${NAMESPACE}" --set image.repository=vault-watchdogs --set image.tag=dev --wait --timeout 120s
kubectl -n "${NAMESPACE}" rollout restart deployment/vault-watchdogs
kubectl -n "${NAMESPACE}" rollout status deployment/vault-watchdogs --timeout=120s
kubectl -n "${NAMESPACE}" logs deployment/vault-watchdogs --tail=20

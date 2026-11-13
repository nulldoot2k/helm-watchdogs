#!/usr/bin/env bash
set -Eeuo pipefail

CLUSTER_NAME="${KIND_CLUSTER_NAME:-vault-watchdogs-lab}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
KIND_CONFIG="${SCRIPT_DIR}/kind-config.yaml"
KUBECONFIG_FILE="${KIND_KUBECONFIG:-${PROJECT_DIR}/.local/${CLUSTER_NAME}.kubeconfig}"
LOCAL_PATH_VERSION="${LOCAL_PATH_VERSION:-v0.0.31}"
INSTALL_METRICS_SERVER="${INSTALL_METRICS_SERVER:-1}"
INSTALL_INGRESS="${INSTALL_INGRESS:-1}"
LAB_HOSTS="${LAB_HOSTS:-vault.test vault-backup.test vault-transit.test watchdogs.test}"

log() {
  printf '[vault-watchdogs-lab] %s\n' "$*"
}

die() {
  printf '[vault-watchdogs-lab] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_command docker
require_command kind
require_command kubectl
require_command helm

docker info >/dev/null 2>&1 || die "Docker is not running or the current user cannot access it"
mkdir -p "$(dirname -- "${KUBECONFIG_FILE}")"

if kind get clusters | grep -Fxq "${CLUSTER_NAME}"; then
  log "Kind cluster already exists: ${CLUSTER_NAME}"
  log "If this cluster was created without port mappings, delete it and run this script again"
  kind get kubeconfig --name "${CLUSTER_NAME}" > "${KUBECONFIG_FILE}"
else
  log "Creating Kind cluster: ${CLUSTER_NAME}"
  kind create cluster \
    --name "${CLUSTER_NAME}" \
    --config "${KIND_CONFIG}" \
    --kubeconfig "${KUBECONFIG_FILE}" \
    --wait 120s
fi

export KUBECONFIG="${KUBECONFIG_FILE}"
CONTEXT="kind-${CLUSTER_NAME}"
kubectl wait --for=condition=Ready nodes --all --timeout=120s

log "Installing local-path provisioner"
kubectl apply -f "https://raw.githubusercontent.com/rancher/local-path-provisioner/${LOCAL_PATH_VERSION}/deploy/local-path-storage.yaml"
kubectl -n local-path-storage rollout status deployment/local-path-provisioner --timeout=120s
kubectl patch storageclass local-path \
  -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}' \
  >/dev/null 2>&1 || true
kubectl patch storageclass standard \
  -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}' \
  >/dev/null 2>&1 || true

if [ "${INSTALL_METRICS_SERVER}" = "1" ]; then
  log "Installing metrics-server"
  helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null
  helm repo update >/dev/null
  helm upgrade --install metrics-server metrics-server/metrics-server \
    --namespace kube-system \
    --set 'args[0]=--kubelet-insecure-tls' \
    --set-string 'args[1]=--kubelet-preferred-address-types=InternalIP\,Hostname' \
    --wait \
    --timeout 180s
fi

if [ "${INSTALL_INGRESS}" = "1" ]; then
  log "Installing ingress-nginx"
  kubectl label node "${CLUSTER_NAME}-control-plane" ingress-ready=true --overwrite >/dev/null
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null
  helm repo update >/dev/null
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.hostPort.enabled=true \
    --set controller.service.type=NodePort \
    --set-string controller.nodeSelector.ingress-ready=true \
    --set controller.tolerations[0].key=node-role.kubernetes.io/control-plane \
    --set controller.tolerations[0].operator=Exists \
    --set controller.tolerations[0].effect=NoSchedule \
    --wait \
    --timeout 180s
fi

HOSTS_BEGIN="# BEGIN vault-watchdogs-lab"
HOSTS_END="# END vault-watchdogs-lab"
HOSTS_BLOCK="${HOSTS_BEGIN}\n127.0.0.1 ${LAB_HOSTS}\n${HOSTS_END}"
HOSTS_BLOCK_FILE="${PROJECT_DIR}/.local/vault-watchdogs-hosts.block"
printf '%b\n' "${HOSTS_BLOCK}" > "${HOSTS_BLOCK_FILE}"
if [ ! -w /etc/hosts ]; then
  require_command sudo
  if sudo -n true 2>/dev/null; then
    log "Updating /etc/hosts with lab hostnames"
    printf '%b\n' "${HOSTS_BLOCK}" | sudo tee /tmp/vault-watchdogs-hosts >/dev/null
    sudo sed -i "/${HOSTS_BEGIN}/,/${HOSTS_END}/d" /etc/hosts
    sudo sh -c 'cat /tmp/vault-watchdogs-hosts >> /etc/hosts'
    sudo rm -f /tmp/vault-watchdogs-hosts
  else
    log "Cannot update /etc/hosts without an interactive sudo password"
    printf 'Run these commands once in your terminal:\n\n'
    printf '  sudo sed -i "/%s/,/%s/d" /etc/hosts\n' "${HOSTS_BEGIN}" "${HOSTS_END}"
    printf '  sudo tee -a /etc/hosts < "%s" >/dev/null\n\n' "${HOSTS_BLOCK_FILE}"
  fi
else
  log "Updating /etc/hosts with lab hostnames"
  sed -i "/${HOSTS_BEGIN}/,/${HOSTS_END}/d" /etc/hosts
  printf '%b\n' "${HOSTS_BLOCK}" >> /etc/hosts
fi

log "Lab is ready"
kubectl get nodes -o wide
kubectl get storageclass
kubectl get pods -A

log "Lab hostnames"
printf '  %s -> 127.0.0.1\n' ${LAB_HOSTS}

cat <<EOF

Cluster context:
  ${CONTEXT}

Project directory:
  ${PROJECT_DIR}

Next steps:
  1. Install Vault from ${PROJECT_DIR}/vault
  2. Install Vault Watchdogs from ${PROJECT_DIR}/charts or ${PROJECT_DIR}/deploy

To remove this lab:
  kind delete cluster --name ${CLUSTER_NAME} --kubeconfig ${KUBECONFIG_FILE}
EOF

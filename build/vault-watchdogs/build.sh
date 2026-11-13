#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tag="${1:-helm-watchdogs-vault:local}"
version="${VAULT_VERSION:-1.20.4}"
docker build --network=host \
  --build-arg "VAULT_VERSION=${version}" \
  --tag "${tag}" \
  --file "${repo_root}/build/vault-watchdogs/Dockerfile" \
  "${repo_root}"

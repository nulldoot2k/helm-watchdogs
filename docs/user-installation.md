# Installing Vault Watchdogs

This document is for users installing the released `vault-watchdogs` product.

## Helm installation

For the public Helm repository:

```bash
helm repo add vault-watchdogs \
  https://nulldoot2k.github.io/helm-watchdogs
helm repo update

helm install watchdogs \
  vault-watchdogs/vault-watchdogs \
  --version 0.1.0 \
  --namespace watchdogs \
  --create-namespace
```

The same chart is also published as an OCI artifact:

```bash
helm install watchdogs \
  oci://ghcr.io/nulldoot2k/vault-watchdogs/vault-watchdogs \
  --version 0.1.0 \
  --namespace watchdogs \
  --create-namespace
```

Use a values file only for deployment-specific settings:

```bash
helm install watchdogs \
  vault-watchdogs/vault-watchdogs \
  --version 0.1.0 \
  --namespace watchdogs \
  --create-namespace \
  -f watchdogs-values.yaml
```

The chart must not require raw keys in `values.yaml`, command-line flags, or
environment variables.

## Manifest installation

Each release publishes a rendered, versioned manifest:

```bash
kubectl apply -f \
  https://raw.githubusercontent.com/nulldoot2k/helm-watchdogs/main/deploy/install.yaml
```

The manifest creates Watchdogs resources only. It does not delete Vault pods,
PVCs, namespaces, or existing Vault configuration.

## Local chart development

For contributors testing a checkout:

```bash
helm lint charts/vault-watchdogs
helm install watchdogs ./charts/vault-watchdogs \
  --namespace watchdogs \
  --create-namespace
```

## Upgrade and uninstall

```bash
helm upgrade watchdogs \
  vault-watchdogs/vault-watchdogs \
  --version 0.2.0 \
  --namespace watchdogs

helm uninstall watchdogs --namespace watchdogs
```

Uninstall removes Watchdogs resources only. Vault data and PVCs are not part of
the Watchdogs release lifecycle.

## Before production

Read the compatibility, migration, security, backup, and rollback sections of
the release documentation before enabling managed recovery.

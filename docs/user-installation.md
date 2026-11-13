# Installing Helm Watchdogs

This document is for users installing the released `helm-watchdogs` product.

## Helm installation

For the public Helm repository:

```bash
helm repo add helm-watchdogs \
  https://nulldoot2k.github.io/helm-watchdogs
helm repo update

helm install helm-watchdogs \
  helm-watchdogs/helm-watchdogs \
  --version 0.1.0 \
  --namespace vault-watchdogs \
  --create-namespace
```

The same chart is also published as an OCI artifact:

```bash
helm install helm-watchdogs \
  oci://ghcr.io/nulldoot2k/helm-watchdogs/helm-watchdogs \
  --version 0.1.0 \
  --namespace vault-watchdogs \
  --create-namespace
```

Use a values file only for deployment-specific settings:

```bash
helm install helm-watchdogs \
  helm-watchdogs/helm-watchdogs \
  --version 0.1.0 \
  --namespace vault-watchdogs \
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
helm lint charts/helm-watchdogs
helm install helm-watchdogs ./charts/helm-watchdogs \
  --namespace vault-watchdogs \
  --create-namespace
```

## Upgrade and uninstall

```bash
helm upgrade helm-watchdogs \
  helm-watchdogs/helm-watchdogs \
  --version 0.2.0 \
  --namespace vault-watchdogs

helm uninstall helm-watchdogs --namespace vault-watchdogs
```

Uninstall removes Watchdogs resources only. Vault data and PVCs are not part of
the Watchdogs release lifecycle.

## Before production

Read the compatibility, migration, security, backup, and rollback sections of
the release documentation before enabling managed recovery.

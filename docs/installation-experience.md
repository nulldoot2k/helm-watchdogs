# Installation experience

## Product rule

Internal architecture may be complex. Client installation must be simple,
safe, and reversible. A client should not need to understand the controller,
Guardian quorum, database schema, or seal implementation to install the
product.

## Helm: recommended path

For a Kubernetes Vault deployment, the normal installation is:

```bash
helm repo add helm-watchdogs https://nulldoot2k.github.io/helm-watchdogs
helm repo update
helm install helm-watchdogs helm-watchdogs/helm-watchdogs \
  --namespace vault-watchdogs \
  --create-namespace \
  --set vault.namespace=vault
```

The chart should auto-discover the Vault StatefulSet, services, pods, and Raft
topology from the namespace. A client only overrides discovery when the Vault
deployment is non-standard:

```bash
helm install helm-watchdogs helm-watchdogs/helm-watchdogs \
  -n vault-watchdogs --create-namespace \
  --set vault.namespace=security \
  --set vault.statefulSet=custom-vault
```

## Raw manifest: one command

The project publishes a rendered, versioned installation manifest:

```bash
kubectl apply -f \
  https://raw.githubusercontent.com/nulldoot2k/helm-watchdogs/main/deploy/install.yaml
```

The manifest creates only Watchdogs resources. It must not delete or mutate
Vault resources during installation.

## First-run initialization

After installation, one command starts a guided bootstrap:

```bash
kubectl -n vault-watchdogs exec deploy/helm-watchdogs -- watchdogs init
```

The wizard performs preflight checks, discovers Vault, detects its current seal
state, initializes the Watchdogs database and Guardian quorum, and prints only
the next safe operator action. It never prints raw key material into logs.

For automation, the same flow accepts one declarative resource:

```bash
kubectl apply -f watchdogs-cluster.yaml
```

## Migration input

Existing Shamir or Transit configuration is detected during preflight. The
operator confirms the source once:

```bash
watchdogs init --from=shamir
watchdogs init --from=transit
watchdogs init --from=none
```

This is an installation or migration input, not a public runtime mode.

## Safety defaults

- Initial policy is `observe`.
- Vault data and PVCs are never deleted by install or uninstall.
- Migration requires a backup confirmation.
- Destructive recovery remains disabled until explicitly enabled.
- Failed preflight leaves the existing Vault untouched.
- Uninstall removes Watchdogs resources only.

## Upgrade and rollback

```bash
helm upgrade helm-watchdogs helm-watchdogs/helm-watchdogs -n vault-watchdogs
helm rollback helm-watchdogs 1 -n vault-watchdogs
```

Database migrations are versioned and run before a controller rollout. A
failed migration blocks the rollout and leaves the previous controller active.

## Distribution contract

Every release publishes:

- Helm chart with a short quick-start
- one rendered raw manifest
- version compatibility matrix
- preflight and migration commands
- upgrade and rollback instructions
- uninstall safety statement

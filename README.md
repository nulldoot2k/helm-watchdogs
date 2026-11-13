# Helm Watchdogs

Helm Watchdogs is an independent key, seal, monitoring, and intelligent
recovery platform for HashiCorp Vault.

It works like a smart operations guardian: it watches Vault continuously,
understands the context of an incident, chooses the smallest safe action,
verifies recovery, and records what happened.

## What it provides

- Native key and seal management
- Cryptographic operations and key lifecycle management
- Vault, Raft, pod, node, and PVC monitoring
- Automatic incident correlation
- Safe auto-unseal and recovery workflows
- Quorum protection and data-safety checks
- Policy-driven remediation
- Audit history, API, and optional UI
- Helm and Kubernetes manifest installation

Watchdogs is designed to be lightweight, explainable, and careful around
running services and persistent data.

## Watchdogs compared with KMS and Transit

| Capability | AWS KMS | Vault Transit | Helm Watchdogs |
| --- | --- | --- | --- |
| Key management | Yes | Yes | Yes |
| Cryptographic operations | Yes | Yes | Yes |
| Vault seal support | External service | Transit seal | Native Watchdogs seal |
| Vault monitoring | No | No | Yes |
| Raft and PVC awareness | No | No | Yes |
| Incident correlation | No | No | Yes |
| Automatic safe recovery | No | No | Yes |
| Policy-based remediation | Limited | Limited | Core capability |
| Data-safety verification | No | No | Core capability |

KMS and Transit focus on cryptographic services. Watchdogs combines that role
with continuous Vault operations and intelligent recovery. Watchdogs is
standalone and does not require AWS KMS, Transit, or HSM.

## Install with Helm

```bash
helm repo add helm-watchdogs \
  https://nulldoot2k.github.io/helm-watchdogs
helm repo update

helm install helm-watchdogs \
  helm-watchdogs/helm-watchdogs \
  --namespace vault-watchdogs \
  --create-namespace
```

## Install with a Kubernetes manifest

```bash
kubectl apply -f \
  https://raw.githubusercontent.com/nulldoot2k/helm-watchdogs/main/deploy/install.yaml
```

## Upgrade

```bash
helm repo update
helm upgrade helm-watchdogs \
  helm-watchdogs/helm-watchdogs \
  --namespace vault-watchdogs
```

## Uninstall

```bash
helm uninstall helm-watchdogs \
  --namespace vault-watchdogs
```

Uninstalling Watchdogs removes Watchdogs resources only. It does not delete
Vault data, Vault PVCs, or the Vault namespace.

## Project status

Helm Watchdogs is under active development. Releases will be published only
after the key service, seal integration, recovery engine, migration workflows,
and data-safety tests pass the release gate.

Vault is the first supported integration. Future integrations will extend the
same platform into broader monitoring, logging, and observability workflows.

For architecture, security, migration, and installation details, see the
[documentation](docs/).

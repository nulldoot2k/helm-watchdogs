# Vault Watchdogs

Independent project for testing Vault monitoring, auto-unseal orchestration, Raft recovery, and safe remediation in a local Kind cluster.

## Initial lab plan

1. Create a Kind cluster with one control-plane node and three workers.
2. Install the required infrastructure addons.
3. Install Vault with Raft storage.
4. Install Vault Watchdogs using Helm or Kubernetes manifests.
5. Run controlled failure scenarios and record the recovery result.

The first implementation should default to observe-only mode. Destructive actions such as peer removal and PVC deletion must require an explicit policy.

## Architecture contract

The project is designed as an independent Vault service manager and native key
management system. It does not require Transit, KMS, HSM, or Kubernetes Secret
for its production design. Watchdogs has one runtime mode: Vault uses
Watchdogs as its own seal and key service. Shamir or Transit are migration
inputs only, never runtime dependencies.

The main differentiator is intelligent, lightweight operations: Watchdogs
correlates Vault and Kubernetes signals, chooses the smallest safe recovery
action, verifies the result, and stops. It is designed to reduce human toil
without introducing unnecessary restarts, PVC changes, polling load, or service
disruption.

Watchdogs is the author's independent infrastructure product: a native key and
seal platform with a Datadog-like operational experience for Vault. It patrols
Vault health, understands incidents, and responds through a safe, explainable
control loop.

See `docs/product-vision.md` for the product charter.
See `docs/installation-experience.md` for the client installation contract.

Read the design before extending the controller:

- `docs/architecture.md`
- `docs/key-management.md`
- `docs/recovery-state-machine.md`
- `docs/data-model.md`
- `docs/security-threat-model.md`
- `docs/roadmap.md`

## Start the lab

The lab script creates the Kind cluster and installs the baseline addons by default:

- local-path provisioner for PVCs
- metrics-server
- ingress-nginx with host ports 80 and 443
- fake lab hostnames in `/etc/hosts`

The lab uses a dedicated kubeconfig at `.local/vault-watchdogs-lab.kubeconfig` and does not switch or modify the current context in the main kubeconfig.

Run:

```bash
./cluster/setup-lab.sh
```

Default hostnames are `vault-backup.test`, `vault-transit.test`, and `watchdogs.test`. Override them with `LAB_HOSTS` when needed.

## Project layout

```text
cluster/       Kind cluster configuration and lab scripts
infra/         Local infrastructure addons
vault/         Vault installation and test configuration
src/watchdogs/  All Watchdogs product source code
charts/        Helm charts
deploy/        Raw Kubernetes manifests
tests/         Failure scenarios and validation tests
docs/          Architecture and recovery runbooks
```

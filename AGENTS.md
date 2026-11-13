# Helm Watchdogs repository rules

## Product boundary

- The product is named Helm Watchdogs.
- Vault is the first supported integration, not the product name.
- Future integrations may cover monitoring, logging, and observability.
- The local Kind cluster is only a development environment and must never be
  included in the public product release.
- Keep source code, public charts, manifests, and user documentation separate
  from local lab files and credentials.

## Go-live rule

Do not create or push the `v1.0.0` tag, publish a release, or announce
production readiness until every item below is complete and verified on a
clean Kubernetes cluster:

- Native key service and cryptographic operation API are implemented and tested.
- Vault seal integration and Shamir migration are implemented without Transit,
  KMS, HSM, or Kubernetes Secret dependencies.
- Key material is never stored in Kubernetes Secrets, `.env` files, logs, or
  ordinary application databases.
- Guardian quorum, recovery lock, key rotation, audit trail, and durable
  storage are implemented and tested.
- Controller reconciliation and leader failover are idempotent and safe.
- Recovery chooses the smallest safe action, never deletes a PVC first, and
  proves Vault health before and after every mutation.
- Node, pod, StatefulSet, Raft, seal, PVC, network, and partial-failure cases
  pass without data loss.
- Helm install, raw manifest install, upgrade, rollback, uninstall, and
  reinstall are tested from a clean cluster.
- RBAC is least privilege and has been tested against every action.
- Image and chart builds are versioned, reproducible, vulnerability-scanned,
  and published only after the release gate passes.
- README, migration, security, backup, rollback, and incident runbooks are
  complete for community users.

Until these checks pass, describe the project as development or release
candidate software. A branch named `release/v1.0.0` is not evidence that the
release is production-ready.

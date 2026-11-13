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
- A compatible Vault Watchdogs Edition includes the native `watchdogs` seal
  provider. A controller that only calls `/sys/unseal` does not satisfy this
  requirement.
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
- The optional UI is functional when enabled: authentication, Vault health,
  Raft and node status, seal state, incidents, remediation history, audit
  events, policies, and safe operator actions are covered by tests.
- Monitoring works without the UI and exposes authenticated API and metrics;
  the UI is a client of the same API rather than a second control plane.
- UI and monitoring must not expose raw key material, unseal shares, tokens, or
  sensitive payloads in pages, API responses, metrics, or logs.

Until these checks pass, describe the project as development or release
candidate software. A branch named `release/v1.0.0` is not evidence that the
release is production-ready.

## Mandatory handoff gate

- Do not hand back this task while the native `watchdogs` seal is only documented, mocked, or parser-tested.
- Handoff requires a reproducible Vault Watchdogs Edition build, a fresh Vault boot using `seal "watchdogs"`, migration of the local Kind Vault from Shamir using `vault operator unseal -migrate`, and a restart test proving `Seal Type: watchdogs` with automatic unseal.
- Handoff must include passing source tests, Helm validation, migration evidence, and a clear list of remaining production blockers. If any gate is red, continue working and do not describe the source as complete or v1.0.0.
- Keep the Kind test isolated to the configured local kubeconfig. Never modify any other Kubernetes cluster.

## Collaboration rule

- When the owner gives an implementation command, execute it directly. Keep
  commentary short and report only completed work, test results, or blockers.
- Do not replace implementation with a long proposal when the requested action
  is technically safe and within the repository scope.
- The controller must never read Vault Shamir keys or call `/sys/unseal`.
  Vault unseal is delegated to the native Watchdogs seal provider. Shamir
  shares are accepted only by the guarded migration ceremony and the
  Watchdogs guardian unlock flow.

Keep intermediate work local. Do not push partial commits to the remote
branch. Before the owner reviews the result, squash the completed work into a
clean history, run the full validation suite, and present the final diff.

## Workstream rule

Use `docs/implementation-plan.md` as the execution checklist. Work through
Streams A to F in dependency order. Do not mark the project complete because a
single stream or demo works; all streams and the clean-cluster failure matrix
must pass first.

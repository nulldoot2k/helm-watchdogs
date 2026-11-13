# Helm Watchdogs implementation streams

This is the execution checklist for the local `release/v1.0.0` work. The
project is complete only when every stream is implemented, integrated, and
verified on a clean Kind cluster. A passing unit test in one stream does not
close the release gate by itself.

## Stream A: Native key and Vault seal

Scope:

- Guardian bootstrap and 3-of-5 quorum ceremony
- In-memory unlock and lock lifecycle
- Encrypted key records and versioned rotation
- Authenticated key-service API with audit events
- Vault seal integration contract
- Shamir migration utility without making Shamir the runtime mode

Done when:

- No raw key is stored in Kubernetes Secret, `.env`, logs, metrics, or the
  operational database.
- Vault can restart and unseal through the Watchdogs key service after an
  explicit guardian unlock.
- Lock, rotation, revocation, quorum loss, and process restart tests pass.

## Stream B: Observation and recovery engine

Scope:

- Vault, Raft, pod, node, StatefulSet, PVC, and network observers
- Incident correlation and durable state machine
- Leader fencing and idempotent actions
- Safe action ladder from observe to approved destructive recovery
- Budgets, backoff, circuit breaker, and rollback verification

Done when:

- The smallest successful action stops the incident.
- PVC deletion is impossible without backup evidence, fresh health data, and
  explicit approval.
- Node failure, pod restart, reschedule, sealed node, lost quorum, stale peer,
  and split-brain tests pass without data loss.

## Stream C: Storage and audit

Scope:

- Durable incident, decision, checkpoint, policy, and audit repositories
- PostgreSQL migrations for production and SQLite test adapter
- Append-only audit records and retention policy
- Encryption boundary and backup/restore procedure

Done when:

- A controller restart or leader handoff resumes from a durable checkpoint.
- Every action has an immutable audit record and correlation ID.
- Database failure fails closed and does not mutate Vault.

## Stream D: API, UI, and CRD

Scope:

- Authenticated API for status, incidents, audit, diagnostics, and approvals
- Lightweight optional UI using the same API
- CRD reconciliation for cluster registration and policy
- Role-based access and redaction tests

Done when:

- UI is optional and adds no required controller pod or heavy runtime.
- API and UI never expose key material, tokens, or sensitive payloads.
- CRD changes are validated, audited, and reflected in the active policy.

## Stream E: Packaging and security

Scope:

- Helm and raw manifest parity
- Namespace, RBAC, probes, PDB, topology spread, and resource budgets
- Versioned image and chart build
- SBOM, vulnerability scan, signature/checksum, and upgrade/rollback

Done when:

- A clean cluster can install, upgrade, rollback, and uninstall safely.
- Two replicas remain available during a rolling update.
- Default resources remain lightweight and destructive features are disabled.

## Stream F: Verification and release

Scope:

- Kind 1 control-plane and 3-worker lab
- Automated failure injection matrix
- Security and data-preservation assertions
- Community documentation and release artifacts

Done when:

- All streams A through E are green on a clean lab.
- The owner reviews the final diff and explicitly says `go-live`.
- Only then may the branch be squashed, tagged `v1.0.0`, and pushed.

## Execution order

```text
A -> C -> B -> D -> E -> F
```

Streams can share interfaces, but no stream may bypass the key, storage, or
recovery safety contracts to make a demo appear complete.

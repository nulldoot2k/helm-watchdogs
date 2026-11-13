# Delivery roadmap

## Phase 0: foundation

- Architecture and threat model
- Two-replica controller
- Leader election
- Observe and assist modes
- Kind failure lab

## Phase 1: standalone Watchdogs core

- Go or Rust controller service
- Typed Vault and Kubernetes clients
- Event-driven observation with bounded polling fallback
- Intelligent correlation and minimal-action policy engine
- Recovery state machine
- Durable incident and action records
- PostgreSQL migrations
- Metrics, health endpoints, and audit events

## Phase 2: Watchdogs seal and Key Service

- Key database schema
- Guardian bootstrap ceremony
- 3-of-5 quorum protocol
- Wrapped key storage
- Short-lived unseal operation
- Rotation, revocation, and recovery lock
- Vault-compatible Watchdogs seal integration
- Installation and upgrade flow on every Vault node

## Phase 3: migration and safe Vault recovery

- Seal and unseal workflows
- Migration from Shamir to Watchdogs seal
- Migration from Transit to Watchdogs seal as an input workflow only
- Pod-only restart workflow
- PVC mount diagnosis
- Raft identity and membership checks
- Snapshot-before-rebuild workflow
- Node fencing and stale-peer handling

## Phase 4: community release

- Helm chart and raw manifests
- UI for health, incidents, policy, approvals, and audit
- Documentation and upgrade guide
- Security review
- Chaos and data-safety test suite
- Versioned API and compatibility policy

## Definition of done for managed mode

Managed mode is not released until every destructive scenario has a passing
test proving that healthy PVCs are retained, quorum is protected, actions are
idempotent, and the audit record is complete.

## Definition of done for intelligent mode

Intelligent mode is not released until failure tests demonstrate that the
controller selects the least disruptive successful action, stops after
verification, remains within resource targets, and produces an explanation for
every decision.

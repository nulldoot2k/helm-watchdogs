# Operational data model

Vault Watchdogs uses its own database for operational state. It does not
replace Vault Raft storage.

## Initial tables

- `clusters`: Vault cluster identity and configured policy
- `nodes`: observed pod, node, Vault node ID, and last health snapshot
- `incidents`: incident lifecycle and severity
- `actions`: ordered recovery actions, attempts, results, and checkpoints
- `key_records`: key IDs, versions, wrapped material, and lifecycle state
- `guardians`: guardian identity, share metadata, and availability
- `approvals`: quorum decisions and approver evidence
- `audit_events`: append-only security and operation events
- `schema_migrations`: database version

## Rules

- All timestamps are UTC.
- Every mutating operation has an idempotency key.
- Encrypted material uses authenticated encryption with associated data.
- Raw key material is never returned by the API.
- Audit events are append-only from the application perspective.
- Database backups are encrypted and tested through restore drills.

PostgreSQL is the first durable backend target. SQLite is allowed only for
single-process development tests and must not be used for an HA deployment.

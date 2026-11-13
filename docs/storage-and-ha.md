# Watchdogs storage and high availability

## Responsibility boundaries

Vault remains the source of truth for secrets and Vault state. Its integrated
Raft storage keeps the Vault data and Raft membership. Watchdogs must never use
its own database as a replacement for Vault storage.

Watchdogs stores operational state only:

- health observations and incident history
- remediation decisions and policy evaluations
- audit records
- encrypted key references, never plaintext unseal shares
- controller configuration and recovery checkpoints

## Recommended storage modes

### Development-only bootstrap

Use temporary Kubernetes Secrets only for isolated development validation. This
is not a production key-management design and is not part of the product
installation contract.

### Single-cluster deployment

Use the native Watchdogs Raft key-authority cluster for durable replicated key
metadata and encrypted key records. Kubernetes Lease remains responsible only
for controller leader election. PostgreSQL is not required.

### Community production deployment

Use a three or five member Watchdogs Raft cluster with encrypted local
snapshots, membership checks, and append-only audit controls. External backup
jobs and backup storage are intentionally out of scope. Raft snapshots remain
mandatory for log compaction and member recovery; they are not an external
backup system. Guardian shares are reconstructed only in memory and erased
after an unlock operation.

## Replica model

The controller runs with at least two replicas. Every replica may observe, but
only the holder of the Kubernetes Lease may execute an action. Lease loss
stops all active remediation immediately. This prevents duplicate unseal,
restart, peer removal, or PVC operations.

The Lease is coordination state, not business data. Losing it must be safe:
another replica can acquire it after the lease expires.

## Raft key-authority implementation order

1. Bootstrap a three or five member Raft cluster with one PVC per member.
2. Persist encrypted key records through the Raft log and local snapshots.
3. Replicate membership, key versions, rotation, and audit events through Raft.
4. Reconstruct the wrapping key in memory after quorum approval, then lock and
   zero the in-memory buffer.
5. Rotate and revoke keys only after a committed Raft entry and audit event.

The controller must call the native key service through an authenticated
operation boundary. It must never contain raw key handling logic.

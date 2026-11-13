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

Use PostgreSQL for durable Watchdogs state and Kubernetes Lease for controller
leader election. PostgreSQL should be deployed separately or provided by the
platform. It is not embedded in the Watchdogs chart by default.

### Community production deployment

Use PostgreSQL with migrations, encryption at rest, backups, retention policy,
and audit append-only controls. Use an external KMS or HSM for the encryption
key that protects Watchdogs key material. Unseal shares are reconstructed only
in memory and are erased after an operation.

## Replica model

The controller runs with at least two replicas. Every replica may observe, but
only the holder of the Kubernetes Lease may execute an action. Lease loss
stops all active remediation immediately. This prevents duplicate unseal,
restart, peer removal, or PVC operations.

The Lease is coordination state, not business data. Losing it must be safe:
another replica can acquire it after the lease expires.

## Key-management roadmap

1. Lab Shamir mode: Kubernetes Secret, local testing only.
2. Encrypted Shamir mode: ciphertext in the database, encryption key in KMS.
3. Guardian mode: threshold approval from independent guardians or HSM-backed
   services before unseal.
4. Rotation and revocation: versioned key records, dual control, audit event,
   and a recovery procedure before any key is retired.

The final product should support these modes through a provider interface. The
controller must not contain provider-specific key handling logic.

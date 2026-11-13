# Security and threat model

## Assets

- Vault unseal material
- Watchdogs Guardian Root Key
- Vault cluster identity and Raft membership
- Recovery policies and approvals
- Audit history

## Threats

- Compromised controller pod
- Compromised Kubernetes service account
- Database snapshot theft
- Malicious or faulty guardian
- Duplicate controllers executing the same action
- Accidental PVC deletion
- Stale node rejoining after a partition
- Key leakage through logs or crash dumps

## Required controls

- Kubernetes Lease leader election
- Separate service accounts for observation, safe actions, and destructive actions
- Guardian threshold quorum
- Envelope encryption for all stored key material
- Network policy between controller, key service, database, and Vault
- Structured audit events without secret values
- Rate limits, backoff, circuit breakers, and action budgets
- Explicit break-glass approval for data-destructive operations
- Failure injection tests before enabling managed mode

## Security promise

Watchdogs protects against ordinary operational failures and accidental
automation mistakes. It cannot protect secrets if all guardians, the database,
and every controller replica are compromised simultaneously. That limitation
must be visible in the product documentation.

# Recovery state machine

Recovery is a state machine, not a shell script. Each transition has a
precondition, timeout, retry budget, audit event, and safe terminal state.

```text
Healthy
  -> Suspected
  -> Diagnosing
  -> SafeAction
  -> Verifying
  -> Recovered

Diagnosing -> Degraded
Degraded   -> AwaitingApproval
AwaitingApproval -> DestructiveAction
Any state  -> Frozen
```

## Diagnosis order

1. Check Kubernetes node condition.
2. Check pod phase, readiness, restart count, and events.
3. Check PVC binding and mountability.
4. Check Vault initialization and seal status.
5. Check cluster ID, node ID, and Raft role.
6. Check quorum and replication indexes.
7. Check active backup or restore operations.

## Safe action ladder

```text
observe
  -> unseal
  -> wait for Raft catch-up
  -> restart pod only
  -> retry join with existing PVC
  -> restore to a new PVC
  -> remove stale Raft peer
  -> delete old PVC only with break-glass approval
```

The engine must stop at the lowest successful action. A healthy PVC is never
deleted to solve a pod or membership problem.

## Node failure rules

- One failed Vault node with quorum intact: keep serving, wait for recovery.
- Pod rescheduled and PVC mounted: verify identity, unseal, and catch up.
- PVC unavailable on the new node: do not delete it; enter degraded state.
- Two failed nodes in a three-node cluster: freeze automated mutation.
- Lost quorum: require an explicit recovery workflow and backup evidence.
- Suspected split brain: fence the old node before any membership change.

## Idempotency and safety

Each incident has an ID and a monotonic action sequence. An action can be
retried safely after a controller restart. Destructive actions require a fresh
health snapshot, quorum validation, approval, and a persisted checkpoint.

# Intelligent and lightweight operation

## What intelligent means

Watchdogs is not a blind restart loop and it is not a generic key server. For
each incident it builds a context from Kubernetes, Vault, Raft, PVC, backup,
and recent action signals. It then chooses the smallest action that can restore
health without risking data.

```text
Signals
  -> correlation
  -> failure classification
  -> policy evaluation
  -> minimal action
  -> verification
  -> incident outcome
```

The decision must answer:

- What failed?
- What is still healthy?
- Is quorum safe?
- Is the data volume available?
- Is a backup or restore active?
- What is the least disruptive recovery?
- What evidence proves recovery?

## Action preference

```text
wait and observe
  -> unseal
  -> retry join
  -> graceful pod restart
  -> recreate pod with the same PVC
  -> restore to a new PVC
  -> Raft membership repair
  -> destructive cleanup with break-glass approval
```

The controller stops as soon as verification succeeds. It must not continue
through the action ladder after the incident is healthy.

## Fast without being aggressive

- Use Kubernetes watch streams for pod, node, PVC, and event changes.
- Use bounded polling as a fallback when a watch is interrupted.
- Coalesce repeated events into one incident.
- Use per-action exponential backoff with jitter.
- Limit one mutating action per Vault cluster at a time.
- Keep a circuit breaker for repeated failures.
- Use deadlines and retry budgets for every action.
- Cache stable metadata such as cluster identity and node IDs.
- Keep the controller stateless between reconciliations except for durable state.

## Resource targets for the first controller

- One active controller process: less than 50Mi memory at idle.
- Idle CPU: less than 20m per replica.
- No sidecar per Vault pod.
- No continuous high-frequency polling.
- No unbounded event or log retention in memory.

These are testable targets, not marketing claims. Load and failure tests must
measure them before a community release.

## Human control

Automation replaces repetitive operations, not responsibility. Observe and
assist actions may be automatic. Raft membership changes, data restoration,
and PVC deletion require policy approval and a complete audit trail.

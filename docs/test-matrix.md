# Failure test matrix

Initial scenarios:

- Vault healthy with all replicas ready. No action must be taken.
- One pod becomes temporarily unready. Keep the PVC and recover safely.
- One pod restarts repeatedly. Retry pod-only recovery before escalation.
- One Raft member cannot join with its existing PVC.
- One worker becomes unavailable.
- Two Vault pods become unavailable. Preserve quorum safety and stop destructive actions.
- A backup or restore job is active during an incident.
- Vault is sealed while Kubernetes pods remain healthy.
- The key service is unavailable during a restart.
- The watchdog itself is restarted during recovery.

Every scenario must record the observed state, action selected, data safety result, and recovery time.

# Kind failure tests

These tests run only against the dedicated Kind kubeconfig:

```bash
./tests/run-lab-tests.sh
```

The suite is intentionally destructive to the local lab only. It seals a Vault
pod, deletes pods, and restarts the Watchdogs deployment. It never targets the
user's default kubeconfig.

Current scenarios:

- healthy cluster and leader Lease
- seal and automatic unseal
- pod restart with PVC retention
- pod deletion with full PVC inventory retention
- Watchdogs restart and leader takeover
- quorum and destructive-action safety

Node hard-failure and data-restore scenarios are separate chaos tests. They
must be added only after the native recovery engine exists, because the current
prototype intentionally has no PVC deletion or Raft repair behavior.

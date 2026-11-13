# Vault integration

Vault is the first supported integration for Helm Watchdogs.

This integration owns Vault-specific discovery, seal and key operations, Raft
health, pod and PVC correlation, recovery policies, and migration workflows.
The Helm Watchdogs core remains product-neutral so additional integrations can
be added later for other services and observability workloads.

# Helm Watchdogs architecture

## Product boundary

Helm Watchdogs is an independent service-management and key-management system
for Vault clusters. It is not a wrapper around Transit, KMS, HSM, or a
Kubernetes Secret. The product has one canonical runtime mode: Vault uses the
Watchdogs seal and key service.

Vault remains responsible for Vault data and its Raft storage. Watchdogs owns
operational state, recovery decisions, key lifecycle, approvals, and audit.

## Product differentiator

Transit, KMS, and similar systems primarily provide cryptographic key
operations. Watchdogs provides an intelligent, lightweight service manager
around Vault. It observes context, correlates signals, selects the least
disruptive valid action, executes it, and verifies the result. Key management
is one capability inside that control loop, not the whole product.

The intelligence must be explainable and bounded. Every decision records the
observations, policy rule, confidence or certainty level, selected action, and
verification result. The first implementation uses deterministic state
machines and policy rules. Future adaptive logic may recommend actions, but it
must not bypass safety policy or quorum checks.

## Runtime components

```text
                         +----------------------+
                         |   Optional UI / API   |
                         +----------+-----------+
                                    |
              +---------------------v---------------------+
              |            Watchdogs Control Plane         |
              |  Observer | Policy | Recovery | Scheduler  |
              +-----+----------------+--------------------+
                    |                |
          Kubernetes/Vault       Native Key Service
                    |                |
          Pods, nodes, PVCs       Key DB + Guardian quorum
                    |                |
                    +------- Audit and event store -------+
```

The control plane runs with at least two replicas. All replicas observe state;
only the Lease holder executes a mutating recovery action. Losing leadership
immediately stops the current action and another replica can continue from a
durable checkpoint.

The UI is optional at installation time and is never a second controller. It
uses the authenticated API for health, incidents, policy, audit, and operator
actions. Monitoring, metrics, and alert events remain available when the UI is
disabled. Neither the UI nor the API returns raw key material, unseal shares,
or sensitive request payloads.

## Core invariants

1. Never delete a PVC as the first recovery action.
2. Never mutate Raft membership without quorum and identity checks.
3. Never auto-remediate when cluster identity is uncertain.
4. Never keep plaintext root keys in Kubernetes Secrets, databases, or logs.
5. Every action is idempotent, bounded by a retry budget, and audited.
6. Data protection has priority over recovery speed.
7. Prefer event-driven observation with bounded polling fallback.
8. Prefer the smallest valid action and stop after recovery is verified.
9. Never interrupt a healthy Vault operation to improve a metric.
10. Keep the control loop lightweight and resource-bounded.

## Runtime mode

There is one Watchdogs runtime: `watchdogs-seal`. It provides the key service,
Vault seal integration, monitoring, policy, and recovery controller as one
product. Safety levels such as observe, assist, managed, and break-glass are
policies inside this runtime, not different seal providers or product modes.

Shamir and Transit are migration sources only. They are not dependencies,
adapters, or runtime modes of Watchdogs.

## Intelligent control loop

```text
Observe -> Correlate -> Diagnose -> Decide -> Act -> Verify -> Learn
    ^                                                   |
    +------------------- durable incident state --------+
```

`Learn` means recording the outcome and improving policy evidence. It does not
mean changing production policy without review. The controller uses event
watchers where possible, coalesces duplicate signals, applies backoff and
circuit breakers, and limits concurrent actions per cluster.

## Source layout

```text
controller/       reconciliation, policy, recovery state machine
key-service/      native key lifecycle and guardian quorum
api/              authenticated API and event streaming
ui/               operational console
storage/          migrations and repositories
charts/           Helm installation
deploy/           raw manifests and lab installation
tests/            failure scenarios and safety assertions
docs/             architecture, security, and recovery contracts
```

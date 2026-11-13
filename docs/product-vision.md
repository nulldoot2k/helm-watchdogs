# Vault Watchdogs product vision

## Identity

Vault Watchdogs is an independent infrastructure product authored and owned by
the project creator. It is a native key and seal platform for Vault, expanded
with intelligent operational management.

The name describes the product behavior: a watchdog patrols the service,
understands its condition, detects abnormal behavior, and responds carefully
before a small fault becomes a major incident.

## Product category

Watchdogs belongs beside systems such as KMS and Transit because it manages key
and cryptographic operations as well as seal operations. It is not limited to
encryption primitives. Its defining
capability is the control loop around those primitives:

```text
Observe -> Understand -> Decide -> Act -> Verify -> Record
```

The product combines:

- native key and seal management
- native cryptographic operation service
- Vault and Kubernetes observability
- business and service health monitoring
- incident correlation
- policy-driven recovery
- Raft and storage safety controls
- audit, history, and operator explanations
- optional UI and API for community users

## Datadog-like inspiration

Datadog is a useful product inspiration for the operational experience:
continuous visibility, correlated signals, clear incidents, and fast feedback.
Watchdogs applies that idea specifically to Vault operations and recovery. It
must remain lightweight, deterministic, explainable, and safe around data.

## Differentiation

```text
KMS / Transit
  -> key operations and cryptographic services

Vault Watchdogs
  -> key and seal operations
  -> continuous Vault understanding
  -> incident intelligence
  -> safe automated recovery
  -> service and business protection
```

The comparison is about product category, not implementation dependency.
Watchdogs is standalone and does not require Transit, KMS, or HSM to provide
its core functionality.

## Cryptographic service boundary

The Native Key and Seal Service is a first-class cryptographic service. Its
initial operation set is:

- secure random generation
- key generation and registration
- key versioning and rotation
- authenticated encryption and decryption
- wrap and unwrap of managed key material
- MAC generation and verification
- key derivation with an explicit context
- revoke, disable, destroy, and recovery lock
- cryptographic audit events without exposing key material

The service owns key material. Controllers and UI clients receive operation
results or short-lived handles, never raw root keys. Every operation is tied to
a key ID, version, policy, caller identity, and audit event.

The initial Vault seal integration should require only the smallest necessary
primitive set: secure randomness, wrap, unwrap, integrity verification, and
key version lookup. Broader cryptographic APIs can be added without coupling
Vault recovery logic to the database or controller.

## Product principles

1. Protect data before restoring availability.
2. Select the smallest action that can solve the incident.
3. Make automation explainable and auditable.
4. Stop immediately after verification succeeds.
5. Keep the agent lightweight and resource bounded.
6. Treat the operator as the final authority for destructive recovery.
7. Make installation simple through Helm or raw manifests.
8. Keep the public architecture coherent instead of exposing internal modes.

## Public product shape

The community release is one product with one canonical runtime:

```text
Watchdogs Server
  ├── Native Key and Seal Service
  ├── Watchdogs Controller
  ├── Guardian Quorum
  ├── Incident and Recovery Engine
  ├── Audit and Policy Store
  ├── API
  └── Optional UI
```

Migration helpers for existing Shamir or Transit Vault clusters are installation
workflows. They do not create separate Watchdogs runtime modes.

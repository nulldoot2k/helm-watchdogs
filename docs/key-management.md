# Native key management design

## Goal

Watchdogs must manage its own key lifecycle without requiring Transit, KMS, or
HSM. The system must still have a clear trust boundary and must not pretend
that a database containing plaintext keys is secure. Watchdogs is the seal and
key service, not an adapter over another key service.

## Key hierarchy

```text
Guardian Root Key (GRK)
  -> split into N guardian shares, threshold M

Watchdogs Key Encryption Key (WKEK)
  -> wrapped by the GRK

Vault Unseal Material
  -> encrypted by the WKEK
```

The GRK is reconstructed only in memory after guardian quorum approval. The
database stores wrapped key material and metadata, never plaintext GRK or
unseal shares.

## Cryptographic operations

The Key Service is also the cryptographic operation boundary. It provides
versioned operations rather than exposing keys:

```text
generate -> key_id/version
wrap     -> ciphertext + key_id/version
unwrap   -> short-lived operation result
encrypt  -> ciphertext + authenticated metadata
decrypt  -> plaintext only to an authorized operation caller
mac      -> tag
verify   -> valid/invalid
rotate   -> new version
revoke   -> unusable version
```

The controller uses operation handles and policy-scoped requests. It must not
read the Guardian Root Key, Watchdogs Key Encryption Key, or raw Vault seal
material from the database.

## Guardian model

The initial target is 3-of-5 guardians. A guardian is an independent
Watchdogs key-service instance with its own identity and encrypted local
share. Guardians must not all run in the same pod or use the same PVC. The
deployment must expose placement rules and a bootstrap ceremony so operators
can distribute guardians across failure domains.

Automatic unseal is possible only after the operator explicitly unlocks the
guardian quorum or enables a documented unattended policy. This is a security
property, not a missing feature: without a trust anchor, no software can both
recover a secret automatically and protect it from a total compromise.

## Unseal flow

1. Observer detects a sealed Vault node.
2. Policy engine verifies cluster identity, quorum, and incident state.
3. Leader requests a short-lived unseal operation from Key Service.
4. Guardians approve the operation according to threshold policy.
5. Key Service reconstructs material in memory only.
6. Recovery engine sends the minimum required shares to Vault.
7. Vault seal status and Raft health are verified.
8. Key material is zeroed where possible and the operation is audited.

## Vault integration

Vault is configured with the Watchdogs seal integration. At startup Vault asks
Watchdogs to unwrap the stored barrier material. The Watchdogs controller then
handles health, quorum, failover, and policy around that key operation.

The install package must provide the compatible Vault integration artifact and
configure it on every Vault node. This is a release blocker: calling
`/sys/unseal` with Shamir shares is only a migration utility and is not the
Watchdogs runtime architecture.

## Key lifecycle

Every key has an immutable ID, version, state, creation event, rotation event,
revocation event, and owner policy. Rotation is additive first: create and
validate a new version, migrate ciphertext, then retire the old version only
after recovery tests pass.

## Prohibited storage

- Kubernetes Secret as the production key store
- plaintext `.env` outside the local lab bootstrap
- plaintext keys in logs, events, metrics, or API responses
- raw keys in PostgreSQL columns
- root keys in the controller process environment

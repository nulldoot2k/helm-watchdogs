# Vault Watchdogs seal provider

This directory contains the native `watchdogs` seal wrapper used by the Vault
Watchdogs Edition. It is compiled into the Vault binary. It is not a Kubernetes
controller workaround and it does not call Vault's `/sys/unseal` endpoint.

The wrapper delegates barrier encryption and decryption to the Watchdogs key
service over an authenticated HTTP API. Guardian quorum unlock remains in the
Watchdogs process. Vault only receives the wrapper result and never receives a
guardian share or the wrapping key.

The provider is intentionally built as an edition of Vault rather than a
runtime plugin because Vault seal types are compiled into Vault's server.

Configuration example:

```hcl
seal "watchdogs" {
  address    = "https://helm-watchdogs-key-service.vault-watchdogs.svc:8090"
  token_file = "/vault/secrets/watchdogs-token"
  key_id     = "vault-barrier"
  ca_file    = "/vault/secrets/ca.crt"
  client_cert_file = "/vault/secrets/tls.crt"
  client_key_file  = "/vault/secrets/tls.key"
}
```

Production deployments must use mTLS. Plain HTTP is intended only for an
isolated local lab.

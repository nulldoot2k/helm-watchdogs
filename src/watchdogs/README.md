# Watchdogs source tree

This directory contains product source code only. Lab setup, Helm packaging,
Vault examples, and deployment scripts remain outside this directory.

```text
src/watchdogs/
├── controller/        reconciliation and leader election
├── key-service/       native key and cryptographic operations
├── seal-integration/  Vault Watchdogs seal integration
├── storage/           database repositories and migrations
├── api/               public API and authentication
└── ui/                optional operations UI
```

The current controller is the first prototype. The other packages are reserved
for the native Watchdogs implementation and must not be replaced by Transit,
KMS, HSM, or Kubernetes Secret adapters.

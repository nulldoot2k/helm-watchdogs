# Installation contract

## Product promise

The client installs one independent product: Helm Watchdogs. The product
contains the native key service, Watchdogs seal integration, controller,
database schema, policy engine, audit, and recovery engine.

There is no Transit mode, KMS mode, HSM mode, or provider-selection matrix.
Those systems are outside the product boundary. Existing Shamir or Transit
configuration is handled only by an explicit migration command.

## Required installation inputs

The client declares:

- Vault version and edition
- Vault installation type: Kubernetes, VM, or bare process
- Vault API and cluster addresses
- Vault storage type and topology
- Vault node discovery method
- Watchdogs database connection
- Watchdogs guardian topology and quorum
- TLS certificates or certificate bootstrap policy
- initial recovery policy
- migration source, if the existing Vault uses Shamir or Transit

The client does not provide raw production keys in Helm values or manifests.

## Canonical installation flow

```text
install Watchdogs
  -> initialize Watchdogs database
  -> bootstrap Guardian quorum
  -> install Watchdogs seal integration on Vault nodes
  -> verify Vault and Watchdogs compatibility
  -> select migration source, if any
  -> backup and run migration ceremony
  -> verify auto-unseal and Raft health
  -> enable recovery policy
```

## Proposed custom resource

```yaml
apiVersion: watchdogs.helm-watchdogs.io/v1alpha1
kind: WatchdogsCluster
metadata:
  name: production
  namespace: vault-watchdogs
spec:
  vault:
    version: "1.20.x"
    platform: kubernetes
    namespace: vault
    statefulSet: vault
    storage: raft
  database:
    type: postgresql
    secretRef:
      name: watchdogs-database
  guardians:
    replicas: 5
    threshold: 3
  migration:
    source: shamir
    enabled: true
  policy:
    initialLevel: observe
```

## Migration sources

`migration.source` can be `shamir`, `transit`, or `none`. This value is used
only during the installation ceremony. After migration, the cluster state is
`watchdogs-seal` and no Transit or KMS component is required by Watchdogs.

## Release artifacts

Every release must publish:

- Helm chart
- rendered raw manifests
- Watchdogs seal integration artifact for each supported Vault version
- database migrations
- compatibility matrix
- migration and rollback runbook
- signed image and checksum metadata

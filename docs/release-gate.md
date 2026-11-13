# Release gate

## Distribution decision

The project will eventually be released as the community product
`vault-watchdogs`. The public name, chart name, image names, documentation, and
release artifacts must use `vault-watchdogs` consistently.

Do not push to a public registry or publish a community release yet.

## Public release is allowed only after

- Native Watchdogs key and seal service is implemented.
- Cryptographic operation API is tested.
- Guardian quorum and recovery lock are tested.
- Controller recovery state machine is complete.
- Node, pod, PVC, and Raft failure scenarios pass.
- No production key is stored in Kubernetes Secret or `.env`.
- Helm and raw manifest installation are both tested from a clean cluster.
- Upgrade, rollback, and uninstall safety are verified.
- Images and charts have versioned, reproducible builds.
- Security and resource tests pass.
- Community documentation and migration runbooks are complete.

## Current phase

Private local development only:

```text
source implementation -> isolated Kubernetes validation -> Helm apply -> failure tests
```

Public publishing is a later release activity, not part of the current lab
installation.

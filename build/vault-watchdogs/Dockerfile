ARG VAULT_VERSION=1.20.4
FROM golang:1.24-bookworm AS builder
ARG VAULT_VERSION=1.20.4
WORKDIR /src
RUN git clone --depth=1 --branch "v${VAULT_VERSION}" https://github.com/hashicorp/vault.git .
COPY src/watchdogs/integrations/vault/seal-provider/go/ /src/internalshared/wrappers/watchdogs/
COPY src/watchdogs/integrations/vault/seal-provider/patches/vault-watchdogs-seal.patch /tmp/vault-watchdogs-seal.patch
RUN git apply /tmp/vault-watchdogs-seal.patch
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags='-s -w' -o /out/vault ./main.go

FROM hashicorp/vault:${VAULT_VERSION}
COPY --from=builder /out/vault /bin/vault

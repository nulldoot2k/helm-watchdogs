FROM golang:1.24-bookworm AS build
WORKDIR /src
COPY go/ ./
RUN go mod download
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags='-s -w' -o /out/watchdogs-key-authority ./main.go

FROM debian:bookworm-slim
RUN useradd --system --uid 65532 watchdogs && mkdir -p /var/lib/watchdogs && chown -R 65532:65532 /var/lib/watchdogs
COPY --from=build /out/watchdogs-key-authority /usr/local/bin/watchdogs-key-authority
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/watchdogs-key-authority"]

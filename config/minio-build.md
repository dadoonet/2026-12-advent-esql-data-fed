# MinIO source build

The demo builds MinIO Community from its official release source. Attempts to
pull `minio/minio:RELEASE.2025-04-22T22-12-26Z` from Docker Hub and the matching
Quay image failed with denied/unauthorized responses during preparation.
This build keeps MinIO as the storage server; it does not substitute another
S3 implementation.

## Pinned provenance

- Official release: [RELEASE.2025-10-15T17-29-55Z](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z).
- Official source commit: `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`.
- [Source archive](https://codeload.github.com/minio/minio/tar.gz/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a)
  SHA-256: `45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841`.
- Go toolchain: `1.24.8`, matching the release's `go.mod` toolchain directive.
- Builder: official `golang:1.24.8-bookworm` multi-platform index
  `sha256:4ed690d6649d63c312b99a6120025ec79ce3b542968a37da53d6236c7c61a848`.
  Its manifest includes Linux ARM64 and AMD64.
- Dependencies follow upstream `go.mod` and `go.sum`; `go mod verify` checks
  downloaded modules before compilation.

The static binary is compiled without source changes, with explicit release
metadata, and copied into a `scratch` runtime image together with upstream's
license and the builder's CA certificate bundle. This is a locally built image,
not an official MinIO binary distribution. The upstream MinIO source is licensed
under AGPL-3.0-or-later; that does not assign a license to this demo repository.
Refer to the exact upstream source above when distributing the image.

Building requires network access to Docker Hub, GitHub's codeload service, and
the Go module proxy/checksum services. The first build can take several minutes
and needs additional disk and memory for the Go compiler and module cache.
The runtime provides no shell or embedded health-check client; readiness is
checked over HTTP by the demo orchestrator.

## Build validation

On 2026-11-05, the Docker build and `--version` smoke check succeeded on
Linux ARM64 in Docker Desktop on an Apple Silicon host:

```sh
docker build -f config/Dockerfile.minio -t santa-esql-advent-minio:source .
docker run --rm santa-esql-advent-minio:source --version
```

The binary reported `RELEASE.2025-10-15T17-29-55Z`, commit
`9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`, and `go1.24.8 linux/arm64`.
The local image ID was
`sha256:f3a3278b11554557dd6c7f829945a17c24002d3fcd9f6cee4a088d34dc42ae57`
(105,502,114 bytes). This local image ID is not a registry manifest digest.
AMD64 compilation has not been tested. End-to-end S3 and federation results
are recorded separately in the demo validation record.

The pinned 2025 release and its dependencies have not received a security audit
as part of this demo. Keep it isolated to the local development network and
localhost bindings. Changing MinIO or Go versions requires rebuilding and
rerunning the complete federation validation.

# Docker infrastructure

The root `compose.yaml` is the canonical integration definition. It currently
contains PostgreSQL, an S3-compatible MinIO server, and the API image.

- Keep one Dockerfile near each deployable area's source unless a documented
  build constraint requires another layout.
- Use the Compose project name `reactorfront-portfolio`.
- Let Compose generate scoped resource names; avoid `container_name`.
- Use project-owned networks and volumes by default.
- Add health checks that represent real readiness rather than process existence.
- Keep host paths, secrets, and local-machine assumptions out of committed
  configuration.

Global Docker cleanup commands are never part of this project's workflow.

## Fixed test infrastructure

- PostgreSQL uses the official `18.4-bookworm` image pinned by manifest digest.
- The API uses the official Python `3.13.14-slim-bookworm` image pinned by
  manifest digest and installs the exact uv lock.
- MinIO is compiled from
  [official source commit](https://github.com/minio/minio/tree/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a)
  `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`, corresponding to the
  [`RELEASE.2025-10-15T17-29-55Z` security release](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z).
  Current community releases are source distributions, so the test image does
  not fall back to an older legacy binary image.

The MinIO build copies its AGPL license into `/licenses/minio/LICENSE`. It is a
separate test-infrastructure process accessed only through the S3 API; the
repository's original code remains MIT-licensed. See
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

# Third-party notices

The root MIT License applies only to original ReactorFront source,
documentation, and synthetic fixtures. Dependencies and infrastructure remain
under their own licenses.

## Runtime infrastructure

| Component | Fixed source | License | Use |
|---|---|---|---|
| PostgreSQL | `postgres:18.4-bookworm` manifest digest in `compose.yaml` | PostgreSQL License | API-owned persistence |
| MinIO | official source commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a` | AGPL-3.0-only | separate S3-compatible test service |
| Python | `python:3.13.14-slim-bookworm` manifest digest in the API Dockerfile | Python Software Foundation License | API runtime |

The MinIO image build copies the upstream license into the resulting image.
MinIO runs as a separate process and communicates with the MIT-licensed API
through the S3 protocol.

## Application and tooling dependencies

Exact Python packages are declared in `apps/api/pyproject.toml` and resolved in
`apps/api/uv.lock`. Exact JavaScript tooling is resolved in `pnpm-lock.yaml`.
Those lockfiles and upstream package metadata are the authoritative inventories
for their respective dependency licenses.

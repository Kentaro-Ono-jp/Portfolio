# Docker infrastructure

The root `compose.yaml` is the canonical integration definition. It currently
contains PostgreSQL, an S3-compatible MinIO server, RabbitMQ, the API image
running HTTP, outbox-dispatch, and result-consumer process roles, an
independent ML worker image, and the Web image.

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
- RabbitMQ uses the official `4.3.2-alpine` image pinned by manifest digest.
  Its AMQP port is loopback-only, the management UI is not enabled, and its
  health check proves that the broker application is running without alarms.
- The API uses the official Python `3.13.14-slim-bookworm` image pinned by
  manifest digest and installs the exact uv lock.
- The ML worker uses the same pinned Python base, installs its independent uv
  lock, generates and checksum-verifies the deterministic CPU PyTorch model in
  the build, and runs as numeric non-root user `10002` without a host port or
  PostgreSQL configuration.
- The Web uses the official Node.js `24.18.0-bookworm-slim` image pinned by
  manifest digest, installs the exact pnpm lock, builds the Next.js standalone
  output, and runs as numeric non-root user `10003`.
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

RabbitMQ declares one durable requested-work exchange and queue through the API
publisher. The `api-outbox` health check opens PostgreSQL and a confirm-capable
broker channel. The API readiness endpoint also includes RabbitMQ as required
by Delivery Specification 0001; `/health` remains process-only.

The `ml-worker` declares a durable result-event queue and routes canonical
started/completed/failed events through confirmed persistent messages. Its
health check verifies the model artifact, MinIO and RabbitMQ reachability, and
an answering Celery worker process. The dedicated worker disables Celery's
unused gossip and mingle cluster bootsteps, while its health-probe control
queues are connection-exclusive for RabbitMQ 4.3 compatibility.

The `api-events` role uses the API image without a host port. Its health check
proves PostgreSQL and RabbitMQ result-topology reachability. It manually
acknowledges only after an atomic receipt/state commit or a verified logical
duplicate; valid ordering races are requeued with a bounded delay and poison
events are rejected without an unbounded loop.

The `web` role exposes only its loopback-bound HTTP port. Its server-side proxy
uses the internal `api:8000` boundary and has no PostgreSQL, RabbitMQ, object
storage, or ML settings. The health check exercises the Web-owned `/health`
route from inside the container.

The canonical Actions runtime source-builds the application images, waits for
the exact eight declared services, and then runs Playwright on the hosted
runner as an external browser client. Playwright is not a ninth Compose
service. AI-agent local verification remains static-only unless the owner
explicitly authorizes local Docker for the exact task.

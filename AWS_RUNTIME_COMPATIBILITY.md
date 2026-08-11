# AWS managed-runtime compatibility

The canonical reader and operator route is the
[portable managed-ephemeral AWS operations guide](AWS_OPERATIONS_GUIDE.md).
This document supplies the deeper application-adapter contract used by that
route.

The public repository keeps Docker Compose as its default evaluation path while
providing explicit runtime modes for the managed AWS profile accepted in
[ADR-0023](ips-microkernel/adr/0023-portable-managed-ephemeral-aws-deployment.md).
These adapters do not create AWS resources and do not grant GitHub Actions AWS
credentials.

## S3 credential boundary

Both API and ML settings select exactly one storage mode:

- `local` requires an explicit endpoint, access key, and secret key. Compose
  uses this mode for the bounded MinIO fixture and path-style addressing.
- `aws` requires the endpoint and all application S3 credential settings to be
  absent. The adapters construct boto3 clients without explicit credentials,
  so the standard provider chain can obtain short-lived ECS task-role
  credentials. Static keys or a custom endpoint in AWS mode fail startup.

An AWS task definition therefore sets `PORTFOLIO_S3_MODE=aws` for API-area
roles and `PORTFOLIO_ML_S3_MODE=aws` for ML, supplies only bucket and Region,
and omits the endpoint, access-key, and secret-key variables. Task-role and
bucket policy construction is implemented by the managed environment root and
described in [its guide](infra/aws/environment/README.md).

## Cognito-compatible OIDC boundary

The Web keeps issuer, authorization, discovery, token, and JWKS endpoints as
separate explicit settings. This is required because a Cognito user-pool
issuer and its browser-facing authorization domain have distinct origins. The
authorization endpoint must match discovery exactly. Token and JWKS
backchannels must match their discovered paths, which preserves the internal
Dex endpoints used by Compose without inferring either endpoint from the
browser URL.

The Cognito Web profile is a public Authorization Code client with S256 PKCE
and no client secret. All production-shaped endpoints require HTTPS. The API
uses `PORTFOLIO_OIDC_MODE=cognito`, requires the capability claim
`cognito:groups`, validates a single exact resource-bound `aud`, and requires
`token_use=access`. An ID token, missing or wrong token purpose, list-valued or
wrong audience, wrong issuer, malformed groups, invalid time, signature, or
algorithm all fail authentication. Local Dex remains
`PORTFOLIO_OIDC_MODE=dex` with the existing `groups` capability claim.

## RabbitMQ 4.2 compatibility route

Normal Compose remains pinned to its ordinary RabbitMQ image. The overlay
[`compose.rabbitmq42.yaml`](compose.rabbitmq42.yaml) pins the independently
rehearsed RabbitMQ 4.2 image. GitHub Actions runs the API and ML runtime groups
again with this overlay, covering durable request and result topology,
publisher confirms, transactional-outbox handoff, late acknowledgement,
retry publication, duplicate/redelivery behavior, reconnect, broker restart,
consumer restart, and worker recovery.

For an operator-controlled local rehearsal, the equivalent project-scoped
command is:

```console
docker compose -p reactorfront-portfolio -f compose.yaml -f compose.rabbitmq42.yaml up --detach --wait
```

Use the canonical verifier for evidence. AI agents do not start local Docker;
the authoritative compatibility execution remains GitHub Actions.

## Container sizing evidence

[`infra/aws/runtime-sizing.json`](infra/aws/runtime-sizing.json) records the
initial valid Fargate task candidates and per-process memory candidates:

| Area | CPU units | Task memory | Processes |
|---|---:|---:|---|
| Web | 256 | 512 MiB | `web` |
| API area | 512 | 1024 MiB | `api`, `api-outbox`, `api-events`, bounded `api-migration` |
| ML | 1024 | 2048 MiB | `ml-worker` |

During the canonical authenticated browser workload,
`scripts/measure_container_resources.py` samples every long-running process,
measures the bounded migration process, records exact source/configuration and
image identities, image sizes, peak memory, peak CPU, process count, sampling
times, and sample count, then checks at least 25% measured-memory headroom.
The exact-head workflow publishes the sanitized
`container-sizing-<run-id>` artifact and job summary.

These measurements are a synthetic GitHub-runner baseline, not production
capacity or live-AWS proof. Image, workload, dependency, or topology changes
must run the measurement again. The later Terraform increment may adopt these
initial candidates only with the exact-head evidence and must retain the
recorded uncertainty.

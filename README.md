# ReactorFront Portfolio

> Status: three vertical slices completed; fourth portable managed-ephemeral
> AWS deployment slice in progress — runtime compatibility, persistent
> bootstrap/bounded runtime authority, frozen persistent deployment IAM, managed
> Terraform lifecycle, and isolated GitHub OIDC automation implemented —
> 2026-08-11

[![Verify](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml/badge.svg?branch=main&event=push)](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml?query=branch%3Amain+event%3Apush)
[![Coverage](https://codecov.io/github/Kentaro-Ono-jp/Portfolio/graph/badge.svg?branch=main)](https://app.codecov.io/github/Kentaro-Ono-jp/Portfolio)
[![License: MIT](https://img.shields.io/github/license/Kentaro-Ono-jp/Portfolio)](LICENSE)

> AI-assisted work starts with [`GIT_AGENTS.md`](GIT_AGENTS.md).

This repository is ReactorFront's public engineering portfolio. It is not a
static profile site or a collection of disconnected demos. It contains one
reproducible, production-oriented system that exposes product reasoning,
application development, applied ML, architecture, security, testing, and
operations as reviewable evidence.

## Product direction

The selected product is a **Document Intelligence and Human Review Platform**.
It will accept PDFs and images, run asynchronous ML processing, produce
structured results, and let authenticated users review and correct those
results with traceable audit events.

Only public, permissively licensed, or synthetic documents and datasets will
be used. Private client or employer materials are outside the project scope.

The completed third vertical slice joins immutable human review to an
explicitly curated synthetic dataset, leakage-aware champion/candidate
evaluation, one reviewed promoted-model manifest, and traceable runtime ML
lineage. Review outcomes never become training data automatically.

The accepted fourth vertical slice adds an explicit managed AWS deployment
path while preserving AWS-free GitHub Actions and local Docker Compose. A
third-party clone deploys only into the third party's AWS account. Runtime
adapters plus the persistent Terraform state/ECR/IAM bootstrap and static
permissions-boundary proof are implemented. The NAT-free managed application
topology is also defined and proven through an AWS-free deterministic plan.
The maintainer deployment IAM is a frozen Console-owned prerequisite:
deployment assumes the exact operator, attests the canonical objects
read-only, and fails closed instead of generating or repairing IAM.
The lifecycle, a real AWS green cycle, and the isolated GitHub OIDC deployment
workflow are implemented as separate governed increments.

## Engineering evidence

The three completed vertical slices demonstrate:

- strict TypeScript and React/Next.js application development
- Python API and applied PyTorch ML engineering
- explicit OpenAPI and asynchronous-event contracts
- PostgreSQL, object storage, and durable job processing
- Docker Compose-based reproducibility
- tests, static analysis, supply-chain checks, and GitHub Actions verification
- observability, failure diagnosis, migrations, and recovery design
- focused issues, pull requests, ADRs, and release history
- OIDC Authorization Code flow with PKCE and a server-owned Web session
- independently authenticated and owner-filtered API resource access
- private source delivery, immutable human decisions, idempotency, concurrency,
  and append-only product audit history
- real-browser security-negative, recovery, leakage-scan, and teardown proof
- synthetic-only feedback candidates and explicit reviewed data curation
- family-disjoint dataset snapshots and reproducible champion/candidate evaluation
- reviewed model promotion, rollback identity, and immutable runtime lineage
- an authenticated model-evidence experience that separates model score,
  measured corpus evidence, and the human final decision

The accepted fourth-slice direction is adding portable Terraform,
ECS/Fargate, RDS PostgreSQL, S3, Amazon MQ, Cognito, bounded automation,
destroy fallback, and residual-resource proof without weakening those three
completed slices or granting ordinary CI AWS write authority.

## Repository structure

```text
Portfolio/
|-- apps/
|   |-- web/                 # TypeScript web application
|   |-- api/                 # Python backend API
|   `-- ml/                  # ML inference and evaluation application
|-- packages/
|   `-- contracts/           # Language-neutral cross-service contracts
|-- ips-microkernel/
|   |-- work-router.md       # iPS Microkernel lifecycle router
|   |-- procedures/          # Focused lifecycle procedures
|   |-- references/          # Durable boundary references
|   |-- selectors/           # Knowledge destination selectors
|   |-- review/              # Independent-review router and procedures
|   |-- ci/                  # CI router, procedures, exceptions, and knowledge
|   |-- architecture/        # Architecture documentation
|   |-- adr/                 # Architecture Decision Records
|   `-- delivery/            # Accepted delivery specifications
|-- tests/
|   |-- integration/         # Cross-service integration tests
|   `-- e2e/                 # Whole-system browser tests
|-- infra/
|   `-- docker/              # Docker-related supporting material
|-- scripts/                 # Shared execution and verification entrypoints
`-- .github/
    `-- workflows/           # GitHub Actions workflows
```

## Accepted architecture decisions

- [ADR-0001: Adopt a modular monorepo](ips-microkernel/adr/0001-modular-monorepo.md)
- [ADR-0002: Target an AI-enabled document intelligence platform](ips-microkernel/adr/0002-target-document-intelligence-platform.md)
- [ADR-0003: Adopt the initial technology stack](ips-microkernel/adr/0003-initial-technology-stack.md)
- [ADR-0004: Keep state ownership in the API and use a transactional outbox](ips-microkernel/adr/0004-api-state-ownership-and-transactional-outbox.md)
- [ADR-0007: Define the authentication, session, and API authorization boundary](ips-microkernel/adr/0007-authentication-session-and-api-authorization.md)
- [ADR-0008: Route AI guidance through progressive disclosure](ips-microkernel/adr/0008-progressive-disclosure-ai-guidance.md)
- [ADR-0013: Name the document governance architecture iPS Microkernel](ips-microkernel/adr/0013-name-ips-microkernel.md)
- [ADR-0021: Govern human feedback, model evaluation, and promotion](ips-microkernel/adr/0021-govern-human-feedback-model-evaluation-and-promotion.md)
- [ADR-0023: Adopt a portable managed-ephemeral AWS deployment profile](ips-microkernel/adr/0023-portable-managed-ephemeral-aws-deployment.md)

Superseded decisions remain under the
[ADR index](ips-microkernel/adr/index.md) as design history.

## Delivery specifications

Use the thin [delivery index](ips-microkernel/delivery/index.md) to select the
governing contract without loading completed and current specifications
together.

The completed model-evaluation boundary is governed by
[Delivery Specification 0003](ips-microkernel/delivery/0003-third-vertical-slice.md)
and its umbrella [Issue #72](https://github.com/Kentaro-Ono-jp/Portfolio/issues/72).
The in-progress managed AWS boundary is governed by
[Delivery Specification 0004](ips-microkernel/delivery/0004-portable-managed-ephemeral-aws-deployment.md)
and its umbrella [Issue #95](https://github.com/Kentaro-Ono-jp/Portfolio/issues/95).
The currently implemented three-slice system and accepted deployment direction
are explained in the
[architecture documentation](ips-microkernel/architecture/index.md). Its
public HTTP operations and generated Web types are inspectable in the
[OpenAPI 3.1 contract](packages/contracts/openapi/openapi.yaml) and
[generated TypeScript](packages/contracts/generated/api.d.ts).

## Contributing and security

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before proposing a change.
- Report vulnerabilities through the private process in
  [`SECURITY.md`](SECURITY.md), never through a public Issue.
- Use only repository-owned synthetic fixtures. Do not submit client,
  employer, personal, or otherwise confidential documents.

The committed Dex configuration is deterministic test infrastructure, not a
production identity provider. The repository is not a persistent hosted
service and accepts no production accounts. Tokens stay behind the Next.js
server boundary, mutations require CSRF protection, the API independently
enforces bearer capabilities and document ownership, and source objects remain
private. See the [security policy](SECURITY.md) and the
[trust-boundary documentation](ips-microkernel/architecture/index.md#trust-boundaries-and-ownership)
for the supported boundary and its limitations.

## AI-assisted engineering evidence

The repository treats AI collaboration rules and reusable CI knowledge as
reviewed engineering artifacts rather than machine-local memory. The explicit
[`GIT_AGENTS.md`](GIT_AGENTS.md) entrypoint reaches a thin
[`ips-microkernel/work-router.md`](ips-microkernel/work-router.md) state
router. Implementation, independent review, CI exceptions, and failure
knowledge are loaded one applicable route at a time instead of as one complete
manual.

The independent reviewer uses an isolated temporary shallow clone, runs
non-Docker static verification, and has comment-only GitHub write authority.
Fast-changing status remains in the governing delivery specification's
tracking Issue, focused Issues, PRs, commits, and Actions runs instead of being
duplicated across local handoffs. Raw chats, hidden reasoning, personal data,
and private context are not published.

## Verification model

GitHub Actions will be the authoritative build and runtime verification
environment. Local Docker Desktop is a development convenience only.

The root [`compose.yaml`](compose.yaml) owns the isolated Compose project
`reactorfront-portfolio`. The canonical verifier checks contracts, generated
types, Web linting, formatting, static types, coverage, production dependency
advisories, migrations, unit tests, and a real
Web/HTTP/PostgreSQL/S3-compatible/RabbitMQ integration path in GitHub Actions.

Install the pinned dependencies and run local static verification from the
repository root. The static-only path neither resolves nor invokes the Docker
CLI. AI-agent work does not start or mutate local Docker Desktop:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py --static-only
```

GitHub Actions runs `python scripts/verify.py` without the flag. That full path
builds and starts only this repository's Compose project, proves the complete
nine-service environment and browser E2E, and stops the project afterward. A
human reviewer may deliberately run the same full command with local Docker,
but it is not the default AI-agent workflow:

```console
python scripts/verify.py
```

Repositories updated from the earlier classic-queue topology may still have a
project-scoped `rabbitmq-data` volume. RabbitMQ rejects redeclaring those queues
as quorum queues. A human who intentionally owns the local Docker action can
stop only this Compose project and remove only its synthetic RabbitMQ volume;
the PostgreSQL and MinIO volumes are preserved:

```console
python scripts/verify.py --reset-local-rabbitmq
python scripts/verify.py
```

The reset is an explicit local upgrade step because queued portfolio fixtures
are disposable, while unrelated Docker resources and the other two project
data volumes are outside its deletion scope.

### Run the current Web, API, outbox, result-consumer, and ML worker boundary

Start the three dependencies, create the deterministic development bucket,
then start the migrated API, its outbox dispatcher, result consumer, and the ML
worker:

```console
docker compose -p reactorfront-portfolio up --detach --build --wait postgres minio rabbitmq
uv run --project apps/api python scripts/prepare_integration.py
docker compose -p reactorfront-portfolio up --detach --build --wait api
docker compose -p reactorfront-portfolio up --detach --build --wait api-outbox
docker compose -p reactorfront-portfolio up --detach --build --wait api-events
docker compose -p reactorfront-portfolio up --detach --build --wait ml-worker
docker compose -p reactorfront-portfolio up --detach --build --wait web
```

The Web application is available at `http://127.0.0.1:53000` and the API at
`http://127.0.0.1:58000`. Open the Web application, choose **Sign in as
synthetic reviewer**, and use the repository-owned identity defined by the
loopback-only [Dex fixture](infra/docker/identity/dex.yaml) before submitting a
PDF of at most 5 MiB. Browser document
operations use an opaque Web session; direct API document calls require a
valid bearer token and capability. Required development ports bind only to
loopback and can be changed with the safe examples in
[`.env.example`](.env.example). The MinIO console is intentionally not
published to the host.

## Accepted fourth vertical slice

The portable managed-ephemeral AWS slice is accepted through
[ADR-0023](ips-microkernel/adr/0023-portable-managed-ephemeral-aws-deployment.md),
[Delivery Specification 0004](ips-microkernel/delivery/0004-portable-managed-ephemeral-aws-deployment.md),
and umbrella [Issue #95](https://github.com/Kentaro-Ono-jp/Portfolio/issues/95).

The selected profile maps Web, API-area, and ML to separate ECS/Fargate
services; PostgreSQL to RDS; object storage to S3 task roles; RabbitMQ to
Amazon MQ; and the OIDC deployment adapter to Cognito. API Gateway HTTP API,
VPC Link, and Cloud Map provide the initial generated HTTPS and private
service-discovery path. The cost-bounded proof is NAT-free, permits no direct
Internet task ingress, and separates persistent bootstrap state from ephemeral
application resources.

Deployment remains an explicit manual action or bounded monthly schedule.
Before billable application creation, the lifecycle must register an
independent destroy fallback. Its normal safety deadline is 60 minutes from
actual registration; a successful lifecycle does not wait for that deadline
and destroys immediately after authenticated smoke and cleanup-session
refresh. Explicitly selected values and `extend` may use the retained
two-hour maximum. A green cycle requires migration,
synthetic seed, health, authenticated asynchronous document proof, external
HTTPS, destroy, and tag plus service-specific residual inventory. Ordinary PR,
fork, Dependabot, and `main` CI paths remain AWS-free and receive no AWS write
authority.

This section distinguishes implemented lifecycle machinery from successful
live proof. The repository implements and verifies the managed-runtime
compatibility boundary for task-role S3, Cognito-shaped OIDC, RabbitMQ 4.2, and
initial measured Fargate sizing. It also defines the portable persistent S3
state backend, immutable Web/API/ML ECR repositories, fixed Permissions
Boundary, environment-isolated purpose roles, trust/pass-role contracts, and
AWS-free allow/deny simulation. Step 4 adds an independent environment state
root for the NAT-free VPC, generated API Gateway endpoint, VPC Link and Cloud
Map ingress, three Fargate services, RDS PostgreSQL 18, S3, Amazon MQ RabbitMQ
4.2, Cognito managed login, injected secrets, bounded logs, exact ownership
tags, and portable outputs. Its fail-closed static plan creates no AWS
resource. The maintainer IAM contract is separately frozen: one owner-admin
maintenance path owns quota and Console changes, while deployment can only
verify the exact source user, assume the exact operator, and read back the
canonical static objects by exact ARN. It cannot mutate IAM or self-heal
drift. See the
[AWS runtime compatibility guide](AWS_RUNTIME_COMPATIBILITY.md) and
[portable AWS bootstrap guide](AWS_BOOTSTRAP.md), plus the
[managed-environment guide](infra/aws/environment/README.md) and
[TTL-first lifecycle guide](infra/aws/lifecycle/README.md). The lifecycle now
provides preflight, immutable CodeBuild image publication, independent
Scheduler/CodeBuild destroy fallback, apply, migration, seed, authenticated
smoke, extend, destroy, status, and residual sweep. Scheduler trust is bound to
the exact persistent environment schedule group rather than an unsupported
individual schedule ARN. An owner-authorized exploratory AWS evaluation
historically consumed the governed `3/3` construction attempts without
reaching a successful hosted cycle. Issue #114 superseded that old numeric
ceiling with a completion-first serialized-attempt boundary and then completed
Step 7: exact source/user/role and static-IAM attestation, three immutable
CodeBuild image digests, verified schedule-first fallback, Terraform apply,
three healthy ECS tasks, migration, synthetic seed, authenticated asynchronous
document smoke over external HTTPS, manual destroy, and 27-category service/tag
residual proof all passed. The fallback was removed only after zero residue.
Cost Explorer was observed once through the separate billing-read role; its
delayed estimate is supporting evidence, not the destroy proof. The ephemeral
environment and deployment images are gone; persistent static IAM, empty ECR
repositories, state backend, and independent controller remain. Issue #116
adds and live-proves one exact GitHub OIDC workflow: owner-started dispatch
maps to `manual`, the first-day 13:00 JST schedule maps to `monthly`, both use
a one-hour normal safety fallback, and neither requires a per-run reviewer or
wait timer. The accepted [manual run](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31482504475)
and [real schedule run](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31489580926)
both passed authenticated asynchronous smoke, immediate destroy, and the
27-category zero-residue sweep. The temporary proof cron was then removed by
[PR #127](https://github.com/Kentaro-Ono-jp/Portfolio/pull/127); only the
permanent first-day schedule remains.

## Completed third vertical slice

The human-feedback model-evaluation slice is complete and traceable through
umbrella [Issue #72](https://github.com/Kentaro-Ono-jp/Portfolio/issues/72),
[ADR-0021](ips-microkernel/adr/0021-govern-human-feedback-model-evaluation-and-promotion.md),
and
[Delivery Specification 0003](ips-microkernel/delivery/0003-third-vertical-slice.md).

Completed machine predictions and human decisions remain separate immutable
evidence. The API-owned feedback export admits no data: it emits only bounded,
sanitized candidates whose source digests already belong to the reviewed
synthetic inventory. A separate reviewed curation change is required before a
repository-owned source can enter a versioned snapshot.

The active `document-type-candidate-v1` classifier is reconstructed from the
fixed 12-sample training split in the 18-sample
`reactorfront-synthetic-documents-v1` snapshot. All source/template families
are disjoint across the 12/2/4 train/validation/test assignment. On the four
held-out synthetic samples the candidate processes 4/4 with macro F1 `1.0`,
per-class recall `1.0`, mean true-label model score `0.99982216`, and no
sanitized failure. These measurements are neither calibrated probability nor
production accuracy, fairness, privacy, robustness, or generalization claims.

One reviewed manifest binds the exact dataset, preprocessing, pipeline,
evaluation policy, report, comparison, artifact, and ontology used at runtime.
Worker build, startup, and readiness fail closed on drift. The previously
accepted `document-type-v1` lineage remains the exact reviewed rollback target;
rollback cannot rewrite prior predictions, reviews, audits, or feedback
candidates.

Measured `completed.v2` lineage crosses the event, API persistence, review
ETag, audit record, OpenAPI, generated Web types, and authenticated result.
Existing results remain explicitly `legacy-unmeasured`. The Web evidence panel
shows exact machine lineage and corpus measurements separately from the
immutable human approval or correction.

The public [model-development summary](apps/ml/MODEL_DEVELOPMENT.md) and
[model card](apps/ml/MODEL_CARD.md) expose the exact reproducible identities,
evidence links, intended use, and limitations. Focused Issues, PRs, reviewed
heads, authoritative workflows or qualified limitations, squash merges, and
merged-main proof are recorded in the
[completion evidence](ips-microkernel/delivery/0003-third-vertical-slice.md#completion-evidence).

The authoritative completion baseline is cold-cache
[run 31203098116](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31203098116)
against exact `main` commit
`ac12aa76645c28b95b0aba250136d1b5353cb5be`. After repository-scoped Actions
caches were removed, the workflow freshly installed the pinned Node, API, ML,
and Playwright dependencies, selected and executed all 9/9 verification groups
and 53/53 test files with none carried or skipped, published measured coverage,
sanitized public artifacts, and removed the isolated Compose project. It used
no repository or organization GitHub Secret, external end-user identity,
maintainer-local runtime state, local AI-agent Docker, or private input data.

Automatic retraining, private-data reuse, OCR, structured field extraction,
cloud deployment, RAG, production identity, persistent hosting, and production-
quality model claims remain outside this completed slice.

## Completed second vertical slice

The authenticated classification-review slice is complete and traceable
through the umbrella [Issue #27](https://github.com/Kentaro-Ono-jp/Portfolio/issues/27),
its focused increments, and
[Delivery Specification 0002](ips-microkernel/delivery/0002-second-vertical-slice.md).

A repository-owned synthetic reviewer signs in through the real OIDC
Authorization Code + PKCE path. The browser receives only an opaque server-
owned session cookie and calls same-origin Next.js routes; the API validates
the OAuth access token again, resolves the stable `(issuer, subject)` principal,
and enforces capabilities plus document ownership. Supported source PDFs remain
private and are streamed only after metadata, size, and SHA-256 verification.

The reviewer can inspect the immutable machine classification, approve it or
record one correction, and view deterministic audit history. The API commits
the terminal decision, idempotency receipt, and audit event atomically while
preserving machine evidence. Real PostgreSQL proof covers concurrent decisions,
replay, stale preconditions, hidden targets, rollback, and populated-schema
migration. The independent ML worker continues to receive no end-user identity
or database access.

The final production-shaped implementation head
[`494c3aea491a5ad4a48c4516642d3d52438c9d10`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/494c3aea491a5ad4a48c4516642d3d52438c9d10)
received an independent
[Approved verdict](https://github.com/Kentaro-Ono-jp/Portfolio/pull/68#issuecomment-5152986667).
[Full run 30711583766](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30711583766)
executed all 9 verification groups and all 48 test files without carried or
skipped evidence; final exact-head
[run 30713515584](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30713515584)
passed with complete evidence lineage. Squash merge
[`fead80df7a4649893b50ce71e947f3f06a518de5`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/fead80df7a4649893b50ce71e947f3f06a518de5)
then passed merged-main
[run 30714445583](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30714445583).

The full browser proof signs in, uploads and processes real synthetic PDFs,
previews the matching private source, approves one result, corrects a
deliberately limited second result, inspects ordered audit events, exercises
security-negative and recovery paths, signs out, scans public artifacts for
private content, and unconditionally tears down only the repository-owned
Compose project. It uses no GitHub Secret, external identity account,
maintainer session, or local Docker state.

This completion is deliberately bounded. Dex remains a loopback-only synthetic
test issuer; no production identity provider or persistent public deployment is
selected. Sessions are process-local, PDFs are limited to one text-bearing page
of at most 5 MiB, and the deterministic two-class model is neither calibrated
nor production-quality evidence. The complete limitation and follow-up set is
recorded in the
[architecture documentation](ips-microkernel/architecture/index.md#known-limitations).

## Completed first vertical slice

The first vertical slice is complete and remains traceable through
[Issue #1](https://github.com/Kentaro-Ono-jp/Portfolio/issues/1),
[Issue #24](https://github.com/Kentaro-Ono-jp/Portfolio/issues/24), and
[PR #25](https://github.com/Kentaro-Ono-jp/Portfolio/pull/25), with the final
delivery record published through
[PR #26](https://github.com/Kentaro-Ono-jp/Portfolio/pull/26). The independently
reviewed implementation head passed the complete nine-group clean-runner
[verification](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29731595926),
and the exact squash merge passed the default-branch
[workflow](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29734332826).

The contract, API-owned document submission, transactional outbox, independent
ML worker, API-owned result persistence, and Web upload/progress/result
boundaries are implemented. The
worker proves canonical Celery task consumption, source-integrity checks,
single-page PDF extraction, reproducible CPU PyTorch classification, and
confirmed at-least-once started/completed/failed result publication. The
`api-events` role validates those messages, commits event receipts and job
transitions atomically, deduplicates logical redelivery, and exposes processing,
completed, or failed state through the existing API.

The Web uses generated OpenAPI types plus runtime Zod validation, keeps the API
base URL and OIDC tokens server-only behind an opaque, bounded Web session,
requires CSRF verification for mutation, and presents accessible queued,
processing, completed, failed, retry, reset, and verified-source states. API
document routes require bearer capabilities and filter status/source access by
the resolved stable owner. The final verification adds Playwright coverage for
the real OIDC sign-in and browser upload,
completed invoice result, terminal ML failure, invalid-file rejection, and
cross-service correlation evidence against the complete nine-service Compose
environment. A final manual full
[main verification](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29734521272)
re-proved the completed tree without maintainer-specific state. After the
`main` Actions caches were removed, a second
[cold-cache dispatch](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29735196072)
re-proved the same exact tree. Repository-owned AI collaboration is defined by
[ADR-0013](ips-microkernel/adr/0013-name-ips-microkernel.md) and the live
`ips-microkernel/` governance root.

## License

Copyright (c) 2026 Kentaro Ono (ReactorFront).

Original source code, documentation, and synthetic fixtures in this repository
are licensed under the [MIT License](LICENSE) unless a file states otherwise.
Third-party dependencies, assets, datasets, and models remain subject to their
respective licenses; introduced runtime infrastructure is recorded in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

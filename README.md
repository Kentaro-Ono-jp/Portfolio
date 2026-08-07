# ReactorFront Portfolio

> Status: third vertical slice accepted for human-feedback model evaluation,
> governed promotion, and runtime ML lineage — 2026-08-02

[![Verify](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml/badge.svg?branch=main&event=push)](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml?query=branch%3Amain+event%3Apush)
[![Coverage](https://codecov.io/github/Kentaro-Ono-jp/Portfolio/graph/badge.svg?branch=main)](https://app.codecov.io/github/Kentaro-Ono-jp/Portfolio)
[![License: MIT](https://img.shields.io/github/license/Kentaro-Ono-jp/Portfolio)](LICENSE)

> AI-assisted work starts with [`GIT_AGENTS.md`](GIT_AGENTS.md).

This repository is ReactorFront's public engineering portfolio. It is not a
static profile site or a collection of disconnected demos. It will contain one
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

The accepted third vertical slice will join immutable human review to an
explicitly curated synthetic dataset, leakage-aware champion/candidate
evaluation, one reviewed promoted-model manifest, and traceable runtime ML
lineage. Review outcomes will never become training data automatically.

## Engineering evidence

The two completed vertical slices demonstrate:

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

Superseded decisions remain under the
[ADR index](ips-microkernel/adr/index.md) as design history.

## Delivery specifications

Use the thin [delivery index](ips-microkernel/delivery/index.md) to select the
governing contract without loading completed and current specifications
together.

The current accepted work is governed by
[Delivery Specification 0003](ips-microkernel/delivery/0003-third-vertical-slice.md)
and its umbrella [Issue #72](https://github.com/Kentaro-Ono-jp/Portfolio/issues/72).
The completed authenticated-review boundary is explained in the
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

## Accepted third vertical slice

The human-feedback model-evaluation slice is accepted and tracked through
umbrella [Issue #72](https://github.com/Kentaro-Ono-jp/Portfolio/issues/72),
[ADR-0021](ips-microkernel/adr/0021-govern-human-feedback-model-evaluation-and-promotion.md),
and
[Delivery Specification 0003](ips-microkernel/delivery/0003-third-vertical-slice.md).

The slice will preserve completed machine predictions and human decisions as
separate immutable evidence. A bounded API-owned export may identify only
repository-owned synthetic review outcomes as feedback candidates; explicit
reviewed curation, rather than runtime behavior, will admit them into a
versioned dataset snapshot.

A first focused implementation increment, tracked by
[Issue #77](https://github.com/Kentaro-Ono-jp/Portfolio/issues/77), establishes
an 18-sample repository-owned synthetic snapshot with fixed family-disjoint
splits, deterministic leakage guards, a machine-readable policy and report
schema, and the unchanged current champion's four-sample held-out baseline.
That bounded baseline records macro F1 `1.0` and mean true-label model score
`0.99982216`; it is neither a calibration nor a production-quality claim.

A second focused implementation increment, tracked by
[Issue #79](https://github.com/Kentaro-Ono-jp/Portfolio/issues/79), builds
`document-type-candidate-v1` deterministically from exactly the accepted 12
training samples and compares its canonical held-out report with the frozen
champion baseline. The candidate matches the bounded champion metrics, passes
every absolute and champion-relative gate, and is eligible for later reviewed
promotion. Its generated artifact remains outside Git history and no runtime
model selection changes in this increment.

A third focused implementation increment, tracked by
[Issue #81](https://github.com/Kentaro-Ono-jp/Portfolio/issues/81), carries the
then-current champion's immutable dataset, preprocessing, pipeline, artifact,
evaluation-policy, and evaluation-report identity through the completed event,
API persistence, review identity, audit history, generated contracts, and Web
validators. Existing v1 rows remain explicitly `legacy-unmeasured`; no
historical lineage is fabricated. Runtime readiness independently derives the
expected lineage from the canonical dataset snapshot, policy, report schema,
and active artifact, so a coherently re-digested report rewrite fails closed.

A fourth focused implementation increment, tracked by
[Issue #83](https://github.com/Kentaro-Ono-jp/Portfolio/issues/83), projects only
eligible terminal reviews through a canonical, API-owned, read-only feedback-
candidate export. Export does not admit data, fit a model, or change runtime
selection.

A fifth focused implementation increment, tracked by
[Issue #85](https://github.com/Kentaro-Ono-jp/Portfolio/issues/85), promotes the
eligible candidate through one reviewed manifest. The ML image generates only
the selected artifact, and startup/readiness fail closed unless its dataset,
pipeline, policy, report, comparison, artifact, and ontology identities match.
The same manifest schema retains the previously accepted classifier as a
reviewed rollback target.

The active classifier is now `document-type-candidate-v1`; its evidence remains
bounded to the tiny repository-owned synthetic corpus. Automatic retraining,
private-data reuse, OCR, structured field extraction, cloud deployment, RAG,
and production-quality claims remain outside this slice. Later increments will
add the bounded Web evidence presentation and publish the final completion
record.

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

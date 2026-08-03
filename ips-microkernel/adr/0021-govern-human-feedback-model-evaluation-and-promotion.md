# ADR-0021: Govern human feedback, model evaluation, and promotion

- Status: Accepted
- Date: 2026-08-02
- Related decisions:
  - [ADR-0001: Adopt a modular monorepo](0001-modular-monorepo.md)
  - [ADR-0002: Target an AI-enabled document intelligence platform](0002-target-document-intelligence-platform.md)
  - [ADR-0003: Adopt the initial technology stack](0003-initial-technology-stack.md)
  - [ADR-0004: Keep state ownership in the API and use a transactional outbox](0004-api-state-ownership-and-transactional-outbox.md)
  - [ADR-0007: Define the authentication, session, and API authorization boundary](0007-authentication-session-and-api-authorization.md)

## Context

The first vertical slice established deterministic asynchronous document
classification across the Web, API, object store, broker, ML worker, database,
and browser. The second slice added authenticated ownership, immutable machine
evidence, one human approval or correction, and append-only audit history.

Those slices prove inference and human adjudication, but they do not yet prove
that a candidate model is measured on data independent of fitting, that its
confidence is evaluated, or that a later runtime prediction can be traced to
the exact dataset, pipeline, artifact, and evaluation evidence that authorized
the model. The current classifier deliberately uses a very small synthetic
training set, and its model card explicitly makes no production-quality claim.

Human review creates valuable product evidence, but treating every review as a
training label would violate the existing trust boundaries. A runtime source
may not be licensed or appropriate for public model development, approval does
not establish data provenance, a correction can contain reviewer error, and
automatic reuse would couple the ML application to API-owned state and end-user
activity. It could also leak source content or actor identity into public
artifacts.

The repository needs a bounded learning loop that demonstrates applied-ML
evaluation and release governance without claiming production quality,
introducing an online model registry, or weakening the completed application
boundaries.

## Decision

### Separate product decisions from learning-data admission

A terminal human approval or correction remains immutable API-owned product
evidence. It may create or support a **feedback candidate**, but it is never a
training or evaluation label merely because the review exists.

Only an explicit curation step may admit a candidate into a later dataset
version. Admission requires all of the following:

- the source is repository-owned synthetic material or has explicit compatible
  provenance and licensing;
- its content identity matches a reviewed corpus manifest;
- the final label is supported by the accepted task ontology;
- actor identity, authorization claims, timestamps, comments, and source text
  not required by the model task are excluded from the learning artifact; and
- the admission is reviewable as a repository change.

Unreviewed runtime documents, unmatched source digests, and private or
unlicensed material are ineligible. The system fails closed rather than
silently assigning them to a dataset.

The API area may provide a bounded export command over API-owned state. The
export contains only the minimum sanitized identities needed for curation and
does not become another deployable application. The ML area does not receive
PostgreSQL credentials, query API tables, or consume end-user identity.

### Use immutable, versioned dataset snapshots

Every training or evaluation run consumes one canonical dataset snapshot. A
snapshot identifies:

- its schema and semantic version;
- every sample and source digest;
- the accepted label and provenance class;
- the template or source family used to prevent related examples crossing
  splits;
- the fixed train, validation, or test assignment; and
- a digest over the canonical manifest.

Train, validation, and test families are separated before candidate fitting.
Exact duplicates, normalized duplicates, conflicting labels, source-identity
reuse, and template-family leakage are deterministic verification failures.
The held-out test assignment is not changed to make a candidate pass.

Repository-owned synthetic data keeps the evidence reproducible and public.
Its measured results describe only the declared corpus and do not establish
real-world generalization.

### Establish a champion baseline before candidate selection

The currently promoted model is the **champion**. A proposed replacement is a
**candidate**. The accepted evaluation policy and champion baseline are
recorded before candidate promotion.

The evaluator produces a canonical machine-readable report containing at
least:

- dataset, split, preprocessing, pipeline, and model identities;
- artifact and manifest digests;
- sample counts and complete-processing counts;
- confusion matrix;
- per-class precision, recall, and F1;
- macro F1;
- a declared confidence-quality measure; and
- every failed, abstained, or invalid sample identity with a sanitized reason.

Every declared sample contributes one minimal sanitized atomic outcome. The
validator derives completeness, confusion, confidence quality, class metrics,
and gates exclusively from those outcomes before comparing any supplied
aggregate. The canonical report digest proves byte identity and integrity; it
does not replace independent derivation of the report's measured claims.

The evaluation policy declares absolute quality gates, champion-relative
regression limits, confidence behavior, completeness requirements, and the
determinism tolerance before a candidate is fitted to satisfy them. A missing
metric, partial run, non-finite value, changed test identity, or unverifiable
digest fails the evaluation.

Confidence is described as calibrated only if a separate validation-based
calibration procedure and held-out calibration gate are implemented and pass.
Otherwise the public result remains an evaluated model score without a
calibration claim.

### Promote through one reviewed repository manifest

There is one canonical promoted-model manifest in the ML area. It binds:

- model and artifact schema versions;
- artifact SHA-256;
- dataset snapshot and digest;
- preprocessing and pipeline versions;
- evaluation-policy version;
- canonical evaluation-report digest; and
- the supported task ontology.

Promotion occurs only through a reviewed repository change after the complete
candidate gates pass. Git history, the focused Issue, PR, independent verdict,
and authoritative workflow provide the promotion audit trail. There is no
runtime mutable model registry, administrator promotion endpoint, or automatic
online retraining in this slice.

The model artifact continues to be generated reproducibly outside normal Git
history. Its expected digest and promotion manifest are committed. Runtime
startup fails closed when the generated artifact does not match the promoted
manifest. Rollback selects a previously accepted manifest through the same
reviewed change process; it does not rewrite prior prediction or review
evidence.

### Preserve runtime lineage across existing boundaries

Every completed processing event and API-owned machine result records enough
immutable lineage to identify the promoted dataset snapshot, preprocessing and
pipeline versions, model version, artifact digest, and evaluation evidence.
The exact transport fields are defined in versioned JSON Schemas and the
OpenAPI contract.

The ML worker continues to receive document, job, correlation, object, and
source-integrity identities only. It does not receive reviewer identity or
review state. The API remains the only owner of PostgreSQL state, validates
lineage before applying a terminal result, and preserves first-terminal-result
and duplicate-delivery guarantees.

The authenticated Web experience may display a bounded model-evidence summary
for the immutable machine result. It does not expose source text, internal
paths, actor claims, raw evaluation samples, or mutable promotion controls.

### Keep verification and claims bounded

GitHub Actions remains authoritative for clean-runner artifact generation,
evaluation, complete Compose runtime, browser proof, evidence capture, and
project-scoped teardown. Local AI-agent verification remains static-only and
does not start Docker Desktop.

Verification must prove both a passing promoted candidate and a rejected
ineligible candidate or mutated lineage. Failure leaves the champion manifest
and all prior machine and human evidence unchanged.

Public documentation reports corpus identity, metrics, limitations, and exact
workflow evidence. It does not claim production accuracy, fairness, privacy,
robustness, calibration, domain generalization, or readiness beyond what the
bounded synthetic evaluation proves.

## Consequences

### Positive

- The completed inference and human-review slices become a traceable model
  lifecycle rather than disconnected application and notebook evidence.
- Review data cannot silently cross into training or public artifacts.
- Candidate comparison is reproducible, leakage-aware, and fixed to explicit
  quality gates.
- Runtime predictions can be traced to exact model-development evidence.
- Promotion and rollback remain reviewable without adding MLflow or a mutable
  production control plane.
- API ownership, ML isolation, at-least-once delivery, and immutable review
  evidence remain intact.

### Costs

- Corpus provenance, split families, canonical reports, and digests require
  new schemas and verification code.
- Result-event, persistence, OpenAPI, and Web contracts must evolve together.
- A meaningful synthetic corpus and confidence evaluation require more work
  than checking one expected classification.
- Reviewed promotion is intentionally slower than automatic retraining.
- Public synthetic evaluation remains bounded evidence and cannot substitute
  for representative production data.

## Rejected alternatives

- Treat every human correction as an automatically trusted training label.
- Let the ML worker query API-owned PostgreSQL or receive end-user identity.
- Select the test split after observing candidate results.
- Report training accuracy as model evaluation.
- Promote whichever artifact is newest at container startup.
- Store a mutable active-model flag in the application database.
- Add MLflow solely to claim model-registry experience.
- Expand to OCR, structured extraction, RAG, or cloud deployment before the
  current classification task has evaluation and lineage evidence.

## Revisit when

- representative licensed data justifies stronger external-validity claims;
- multiple independently deployed model versions require a real registry or
  controlled rollout plane;
- online feedback volume and measured latency justify automated curation or
  retraining;
- a new document task requires task-specific metrics, annotation, or lineage;
  or
- managed deployment creates a separate model-signing, attestation, or secrets
  requirement.

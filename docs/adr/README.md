# Architecture Decision Records

ADRs record important technical decisions, their context, alternatives, and
consequences.

Use a four-digit sequence and a short descriptive name:

```text
0001-modular-monorepo.md
```

Do not rewrite the history of an accepted decision. When a decision changes,
add a new ADR and mark the old one as superseded.

## Accepted records

- [ADR-0001: Adopt a modular monorepo](0001-modular-monorepo.md)
- [ADR-0002: Target an AI-enabled document intelligence platform](0002-target-document-intelligence-platform.md)
- [ADR-0003: Adopt the initial technology stack](0003-initial-technology-stack.md)
- [ADR-0004: Keep state ownership in the API and use a transactional outbox](0004-api-state-ownership-and-transactional-outbox.md)
- [ADR-0007: Define the authentication, session, and API authorization boundary](0007-authentication-session-and-api-authorization.md)
- [ADR-0008: Route AI guidance through progressive disclosure](0008-progressive-disclosure-ai-guidance.md)
- [ADR-0009: Reconcile reusable governance knowledge through reviewed updates](0009-reviewed-governance-knowledge-reconciliation.md)
- [ADR-0010: Preserve every reusable review candidate in one verdict](0010-lossless-review-candidate-capture.md)
- [ADR-0011: Prove complete review diffs without a local merge base](0011-deterministic-shallow-review-diff.md)

## Superseded records

- [ADR-0005: Make AI collaboration guidance repository-owned](0005-repository-owned-ai-collaboration.md)
- [ADR-0006: Consolidate repository-owned AI guidance](0006-consolidate-ai-guidance.md)

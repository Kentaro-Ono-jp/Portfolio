# ADR-0002: Target an AI-enabled document intelligence platform

- Status: Accepted
- Date: 2026-07-18

## Context

This portfolio is intended to maximize credibility in high-value freelance
engagements. It must demonstrate more than an isolated frontend, CRUD API, or
model notebook. It needs one coherent product through which a reviewer can
inspect product reasoning, application engineering, ML integration, cloud
architecture, security, operations, and technical leadership.

Trying to cover every software market in one repository would create a shallow
technology catalogue. The strongest adjacent target area is the intersection
of AI-native full-stack development, Python backend engineering, applied ML,
cloud/platform design, and architecture leadership.

Generic CRUD applications and generic retrieval-augmented chat applications
are too easy to reproduce without demonstrating production engineering depth.

## Decision

Build a **Document Intelligence and Human Review Platform**.

The platform will accept business documents such as PDFs and images, process
them through an asynchronous ML pipeline, produce structured results, and let
an authenticated user review, correct, and approve those results.

The product must eventually expose evidence of the following capabilities:

- document upload, validation, and lifecycle management
- asynchronous preprocessing, inference, and postprocessing
- structured extraction or classification with confidence information
- a human review and correction workflow
- model, prompt, pipeline, and evaluation version traceability
- audit events for material user and system actions
- explicit API and asynchronous-event contracts
- secure data handling and authorization boundaries
- logs, metrics, traces, health checks, and failure recovery
- repeatable local and GitHub Actions verification
- a credible AWS deployment design managed as code

Use only public, permissively licensed, or synthetic documents and datasets.
Do not reuse private employer or client code, specifications, prompts, models,
documents, datasets, or other non-public knowledge.

## Target engagement areas

This product is optimized to support discussions for these adjacent roles:

- senior TypeScript/React full-stack engineer
- Python backend and API engineer
- applied AI or ML application engineer
- cloud-native and platform engineer
- technical lead or solution architect

It does not claim competence in unrelated markets such as native mobile,
embedded systems, game development, SAP, or mainframe modernization.

## Reviewer proof

A reviewer must be able to assess the project at three levels:

1. Read the repository and understand the product, boundaries, tradeoffs, and
   operating model without running it.
2. Run one documented verification entrypoint and obtain deterministic build,
   test, inference, and integration evidence.
3. Inspect focused issues, pull requests, ADRs, tests, security checks, and
   operational artifacts to understand how decisions were made.

## Consequences

### Positive

- One product naturally exercises web, API, ML, data, asynchronous processing,
  security, operations, and cloud concerns.
- The human-review and audit flow differentiates the project from a demo-only
  AI chatbot.
- Public or synthetic data keeps the project reviewable and legally isolated
  from client work.
- The scope supports incremental delivery without hiding the final system goal.

### Costs

- Document processing introduces file-handling, job-lifecycle, and test-data
  complexity.
- Meaningful ML proof requires evaluation evidence, not only an inference API.
- Security and observability must be designed early enough to avoid appearing
  as decorative late additions.
- The complete product must be delivered in vertical slices to remain
  finishable.

## Explicit non-goals

- A static-only profile or resume site
- A collection of unrelated technology demonstrations
- A generic chatbot whose domain model is an AI framework
- Training or self-hosting a large foundation model
- Reproducing any private client system

## References

- [Findy Freelance Market Report 2026](https://freelance.findy-code.io/articles/market-report_202603)
- [Geechs IT Freelance Market Report, 2026 Q1](https://www.geechs.com/newsrelease/20260512_ankenbairitsu/)
- [GitHub Octoverse 2025](https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/)

# AI collaboration

This directory is the shared, repository-owned entrypoint for AI-assisted
development of the ReactorFront portfolio. It contains durable operating rules
and curated prompts, not a copy of one agent's memory or a task transcript.

## Source-of-truth order

Use the first applicable source in this order:

1. [Accepted ADRs](../adr/README.md) and
   [Delivery Specification 0001](../delivery/0001-first-vertical-slice.md) for
   product and structural decisions.
2. [`AGENTS.md`](../../AGENTS.md), [`CLAUDE.md`](../../CLAUDE.md), and this
   directory for stable AI collaboration rules.
3. [Umbrella Issue #1](https://github.com/Kentaro-Ono-jp/Portfolio/issues/1),
   the active focused Issue and PR, commits, review verdicts, and GitHub Actions
   for live project state and evidence.
4. Local memory, task conversation, summaries, and handoff text as
   non-authoritative orientation only.

When sources conflict, do not silently combine them. Stop the intended
mutation, inspect the smallest relevant live state, and report the discrepancy
to the repository owner.

## Required reading

For a fresh task:

1. Read the root agent entrypoint and this file.
2. Read the root README, accepted ADRs in numeric order, Delivery Specification
   0001, and the nearest area README.
3. Follow the [operating contract](operating-contract.md).
4. Use the [task lifecycle](task-lifecycle.md) to perform bounded live checks.
5. Apply the [evidence policy](evidence-policy.md) when updating Issue
   checklists or completion records.

## Durable guidance

- [Operating contract](operating-contract.md): authorized actors, mutation
  boundaries, trust assumptions, discrepancy handling, and public safety.
- [Task lifecycle](task-lifecycle.md): targeted orientation, implementation,
  independent review, merge, and cleanup.
- [Evidence policy](evidence-policy.md): focused and umbrella Issue checklist
  reconciliation.
- [Prompt library](prompts/README.md): curated bootstrap, independent review,
  and post-merge prompts.
- [ADR-0005](../adr/0005-repository-owned-ai-collaboration.md): why this
  guidance is repository-owned.

## Live state is not duplicated here

Issue #1 is the live portfolio ledger. Focused Issues define the active scope,
failure model, non-targets, and acceptance criteria. PRs, verdict comments,
commits, and Actions runs supply implementation evidence.

Do not add a second manually maintained current-status document here. A task
must use narrow live checks against the relevant GitHub records before it
mutates project state.

## Public-safety boundary

Commit only portable, project-relevant guidance. Do not publish raw chats,
hidden reasoning, private system prompts, credentials, personal facts, private
company or client context, unrelated project identifiers, or machine-specific
paths. Local memory is inventoried separately and is never copied wholesale
into this directory.

Changes to this contract require a focused Issue and reviewed PR. A task or
local-memory instruction cannot silently override it.

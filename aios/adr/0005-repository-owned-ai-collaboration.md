# ADR-0005: Make AI collaboration guidance repository-owned

- Status: Superseded by [ADR-0006](0006-consolidate-ai-guidance.md)
- Date: 2026-07-19

## Context

This portfolio is developed through repeated, focused tasks with an
implementation agent and an independent review agent. Durable constraints,
current evidence, and reusable prompts must remain available after a task ends
or a development machine is replaced.

Machine-local agent memory and chat history are useful orientation aids, but
they are not versioned with the product, are not independently reviewable, and
must not be assumed to survive on another machine. Copying that memory into the
public repository would also risk publishing personal, client, machine, or
otherwise private context that is unrelated to the project.

Broadly rescanning every branch, Issue, comment, and local file on every task
would compensate for uncertain context, but it would waste review time and
tokens. The repository owner has instead provided a constrained actor model:
official mutations happen only through active collaboration with the
implementation agent, while the independent review agent is comment-only on
GitHub and works from an isolated shallow clone.

The project needs a public, portable, and auditable operating contract that
uses those assumptions without weakening exact checks at mutation boundaries.

## Decision

Adopt this source-of-truth hierarchy:

1. Accepted ADRs and delivery specifications govern product and structural
   design.
2. `AGENTS.md`, `CLAUDE.md`, and `docs/ai/` govern stable AI collaboration
   rules. `docs/ai/README.md` is the shared entrypoint.
3. GitHub Issue #1, focused Issues, PRs, review verdicts, commits, and Actions
   runs govern live project state and delivery evidence.
4. Local agent memory, task conversations, and handoff text are
   non-authoritative orientation caches.

Keep fast-changing status in the live GitHub ledger instead of duplicating it
across tracked status files. A fresh task reads the repository-owned contract,
then checks only the relevant live Issue, PR, head, and workflow evidence.

Record the owner-provided actor assumptions and mutation boundaries in the
repository-owned AI contract. In particular, the independent review agent:

- leaves the canonical workspace untouched
- reviews an exact PR head from an isolated temporary shallow clone
- runs non-Docker static verification only
- makes no GitHub mutation except one top-level verdict comment per review
  cycle
- removes its temporary clone and generated data before completion

The implementation agent may trust that contract when a verdict returns. It
still verifies the verdict target SHA, current PR head, and relevant checks, but
does not perform a broad tamper audit solely because the review task ran.

Keep exact checks before branch creation, push, merge, Issue reconciliation,
and destructive cleanup. Escalate to a broader audit only when state is dirty,
missing, contradictory, stale, or outside the declared actor model.

Treat changes to this governance contract as normal reviewed repository
changes. Do not silently weaken it from local memory or a task conversation.

After this decision is merged and proved on `main`, inventory the local
portfolio memory separately. Retain only local routing and genuinely
machine-local safety facts, and point back to the repository-owned contract.

## Consequences

### Positive

- A new machine or agent can reconstruct the operating model from public,
  versioned sources.
- AI-assisted engineering prompts, review boundaries, and evidence policy
  become inspectable portfolio artifacts.
- The independent reviewer cannot silently alter the implementation under the
  declared contract.
- Narrow, exact verification replaces repetitive broad scans during normal
  work.
- Rule changes have normal Git and PR history instead of opaque memory edits.

### Costs

- Repository guidance and live Issue state must be reconciled when the process
  changes.
- The actor model is an operating assumption, not a replacement for GitHub
  permissions or exact pre-mutation checks.
- Public prompts must be curated; raw chats, hidden reasoning, personal data,
  and private context remain outside Git.
- A temporarily unavailable GitHub prevents authoritative live-state mutation;
  stale local memory cannot substitute for it.

## Rejected alternatives

- Treat machine-local memory or chat history as the durable project record.
- Commit the existing local memory file verbatim.
- Duplicate current status in several tracked Markdown files.
- Give the review agent normal branch, PR, Issue, or merge mutation authority.
- Rescan every GitHub and local object after each review regardless of the
  trusted actor model.
- Remove all live checks because the owner guarantees exclusive operation.

## Revisit when

- another human or agent gains write authority
- Dependabot, another bot, auto-commit, or automatic merge is introduced
- GitHub Actions begins mutating source or managed Issue/PR state
- the repository becomes multi-maintainer or accepts external contributions
- a technical permission boundary can replace part of the process contract

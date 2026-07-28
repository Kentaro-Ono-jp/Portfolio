# ADR-0008: Route AI guidance through progressive disclosure

- Status: Accepted
- Date: 2026-07-26
- Supersedes: [ADR-0006](0006-consolidate-ai-guidance.md)
- Tracking issue: [#32](https://github.com/Kentaro-Ono-jp/Portfolio/issues/32)

## Context

ADR-0005 made durable AI collaboration guidance repository-owned. ADR-0006
then removed duplicated rules by consolidating eight AI files into one
implementation contract and one review contract. That correction succeeded:
each rule gained a clearer canonical home and cold tasks read fewer files.

The consolidated surface continued to grow with the project. Before this
decision, the implementation contract had 291 lines, the review contract 136,
and the CI playbook 227. More importantly, their responsibilities mixed:

- authority, live checks, implementation, publication, merge, evidence, and
  cleanup shared one implementation document
- review setup, inspection, verdict publication, and platform-specific cleanup
  shared one review document
- normal staged preflight, local orchestration, a Markdown-only exception,
  failed-run triage, post-merge reconciliation, reusable decision rules, and
  historical evidence shared one CI document
- cold-start routing still instructed agents to read all accepted ADRs and
  delivery specifications in numeric order

This creates a different cost from ADR-0006's original duplication problem.
Rules may remain unique yet compete for attention because an agent loads
procedures, exceptions, and history unrelated to its current state. Historical
CI knowledge intended for conditional reuse can dilute the normal preflight
algorithm it is meant to improve.

Returning to the old eight-file topology without a routing contract would
reintroduce duplication. Keeping the exact two-file topology would let
unbounded context growth continue.

## Decision

Adopt progressive disclosure for repository-owned AI guidance.

### Thin tracked entrypoints

Keep these stable entrypoints, but make each a router or compatibility pointer:

- `GIT_AGENTS.md`: repository boundary and route to AI work selection
- `AI_GUIDANCE.md`: tool-neutral pointer to `GIT_AGENTS.md`
- `docs/ai/README.md`: ordered implementation-state router
- `docs/ai/PR_REVIEW.md`: independent-review permission and state router
- `.github/workflows/CI_PLAYBOOK.md`: CI-state router

Entrypoints do not contain complete procedures or historical ledgers.

### State-directed procedures

Represent implementation as explicit focus, implement, publish, correct,
merge, and reconcile states. Represent independent review as setup, inspection,
verdict, and cleanup states. Each procedure declares:

- when it is read
- its required inputs or preconditions
- the current action
- explicit guard, recovery, or completion outcomes
- the next or return transition

Routers use ordered first-match selection. An agent opens one selected route
at a time and does not preload siblings. A loop-back is valid only after state
changes, a bounded retry becomes available, or a deterministic fallback
produces new evidence.

### Conditional references and knowledge

Keep actor authority, bounded live checks, public safety, evidence policy, and
local tool authorization in canonical reference files. A procedure loads one
only when its stated condition applies, then returns to the caller.

Split CI knowledge by changed boundary or failure signal. Normal staged
preflight selects only relevant knowledge leaves. The Markdown-only rule is an
explicit exception file, and historical failed-run evidence remains beside
its reusable decision rule without loading on the default path.

This is responsibility separation, not permission to duplicate rules. Every
durable rule retains one canonical home; other files route to it.

### Deterministic lifecycle defaults

Keep one owner-confirmation STOP: selecting the initial focused slice or
materially redefining its outcome, scope, non-targets, or accepted design.
After a slice is accepted, exact evidence drives Ready, merge, checklist
reconciliation, and scoped cleanup without another confirmation pause.

Machine-qualify the Markdown-only CI exception. Route Docker-backed proof to
GitHub Actions rather than requesting local Docker. Delete only verified
task-owned temporary data and branches whose exact merged state is proved;
retain an uncertain target without blocking other reconciliation. Recover
dirty, moved, or contradictory live state through bounded refresh,
re-evaluation, and safe rerouting. Return to focus only when recovery changes
the slice materially.

### Targeted design lookup

Use indexes to select the governing delivery specification and implicated
ADRs. Do not read every accepted record at cold start. Read only the relevant
specification sections, decisions, live tracking Issue, focused Issue, and
nearest area documentation needed by the known scope. Broaden only after a
concrete dependency or conflict.

### Executable topology

Extend the existing documentation checker to verify:

- the exact routed file inventory
- role and canonical-rule markers
- required route links and reachability from tracked entrypoints
- required headings for procedures, references, and knowledge leaves
- thin-router line budgets
- ordered and non-eager routing language
- preservation of every recorded failed CI run in one knowledge leaf
- public-safety scanning across the complete routed surface

Keep `python scripts/verify.py` as the sole root verification entrypoint.

### Preserved safety invariants

This decision changes information loading and replaces repeated confirmation
gates with deterministic policy. It does not weaken proof. Preserve:

- accepted design, durable guidance, live GitHub evidence, and local
  orientation as distinct authority layers
- deliberate owner selection of initial and materially redefined slices
- exact evidence guards for Ready, merge, checklists, cleanup, branch deletion,
  and machine-qualified CI exceptions
- focused Issues, exact branches and heads, Draft PR checkpoints, independent
  review, and merged-main evidence
- isolated, static-only, one-comment independent review with verified cleanup
- bounded normal live checks and exact mutation checks
- evidence-backed focused and umbrella checklists
- public exclusion of secrets, private context, local paths, raw chats, hidden
  reasoning, and unfiltered memory
- fast-changing status in live GitHub records rather than tracked handoffs

ADR-0006 remains historical evidence of why duplicated topic files and
vendor-named entrypoints were rejected. Its exact two-file topology is the
superseded portion.

## Consequences

### Positive

- A task loads the current procedure and only conditionally relevant knowledge.
- Exceptions and historical failures no longer dilute normal workflow steps.
- Explicit transitions make correction and re-entry behavior inspectable.
- Canonical ownership preserves ADR-0006's anti-duplication benefit.
- Structural tests prevent routers from silently becoming manuals again.
- New delivery slices do not require cold reading of completed design history.

### Costs

- More files and links must remain navigable and tested.
- A poorly classified state can select the wrong leaf, so router precedence,
  deterministic recovery, and the single slice STOP are part of the contract.
- Some tasks legitimately read several files sequentially; progressive
  disclosure limits eager loading but cannot erase already read context.
- New reusable knowledge requires choosing or adding one canonical leaf.

## Rejected alternatives

- Keep the growing consolidated documents and shorten wording only.
- Restore the pre-ADR-0006 file set without unique ownership or routing.
- Put every rule in one machine-readable configuration file.
- Duplicate global authority and safety rules inside every procedure.
- Load every exception and historical failure before normal implementation.
- Remove historical evidence instead of routing it conditionally.
- Use unrestricted goto-style transitions without changed-state or guard
  rules.

## Revisit when

- normal workflows require several reference leaves to perform their default
  case
- router ambiguity or context thrashing appears in repeated tasks
- technical permissions replace part of the process authority model
- another actor or source-mutating automation is introduced
- a machine-readable workflow engine can improve routing without obscuring the
  public contract

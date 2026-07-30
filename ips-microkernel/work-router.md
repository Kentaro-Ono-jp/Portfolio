# iPS Microkernel work router

<!-- ips-role: router -->
<!-- ips-rule: progressive-disclosure -->

This router applies progressive disclosure to repository-owned iPS Microkernel
guidance. Read this file, choose the first matching state below, and open only
that route. Do not preload the other routes, the whole `ips-microkernel` tree,
or its human-only architecture README.

## Authority snapshot

Accepted design governs product structure; repository guidance governs durable
collaboration; the governing tracking Issue, focused Issue, PR, commits,
verdicts, and Actions runs govern live state; local memory and earlier
conversation are orientation only.

The detailed actor and permission contract has one canonical home in
[authority](references/authority.md). Read it only when the actor model is
contested or a durable mutation needs its exact default policy.

When sources conflict, use the
[live-state and discrepancy route](references/live-state.md) instead of silently
combining them or requesting a broader decision.

## Select the first matching state

The order below is precedence. Once a condition matches, do not inspect later
routes until the selected route returns here with changed state.

1. **Independent initial review or re-review:** use the dedicated
   [review router](review/router.md).
2. **A complete candidate is staged, a GitHub Actions run failed, a local
   rehearsal is blocked, a Markdown-only exception is requested, or CI
   knowledge must be reconciled:** use the
   [CI router](ci/router.md).
3. **An exact feature merge is proved and reusable non-CI process or review
   knowledge must be reconciled:** use
   [governance knowledge reconciliation](procedures/governance-reconcile.md).
4. **State is dirty, stale, contradictory, unavailable, or outside the actor
   model:** use [live-state and discrepancy handling](references/live-state.md).
5. **A development tool or runtime is missing or mismatched:** use
   [local tool authorization](references/local-tools.md).
6. **No accepted focused scope or exact branch exists, or material scope has
   changed:** use [focus](procedures/focus.md).
7. **An accepted focused Issue and exact branch exist, but implementation is
   not a complete staged candidate:** use
   [implement and verify](procedures/implement.md).
8. **The verified candidate is ready to commit, push, or publish as a Draft
   PR, including a follow-up push:** use [publish](procedures/publish.md).
9. **An exact-head `Changes requested` verdict contains findings whose
   disposition is incomplete:** use
   [review finding adjudication](procedures/adjudicate.md).
10. **Complete adjudication records one or more required corrections and no
    exact owner waiver accepts them:** use [correct](procedures/correct.md).
11. **An independently approved exact head, a fully adjudicated exact head
    with zero required corrections, or an exact reviewed head with a recorded
    owner waiver has its required proof:** use
   [merge](procedures/merge.md).
12. **The PR is merged and evidence or cleanup remains:** use
   [reconcile](procedures/reconcile.md).

If no condition matches, refresh bounded live state once and repeat the ordered
selection. If no focused slice exists, use focus. Otherwise preserve the last
exact checkpoint, report the routing defect, and do not invent a mutation.

## Design lookup without bulk reading

Do not read all ADRs or delivery specifications at cold start.

- Use the [delivery index](delivery/index.md) to select the one governing
  specification and its live tracking Issue. Read only the relevant sections
  needed by the focused scope.
- Use the [ADR index](adr/index.md) to select only decisions implicated by
  the requested boundary.
- Read a nearest area README only after the affected area is known.
- Broaden design reading only when an observed dependency or conflict requires
  it.

## Navigation contract

- A workflow may route to one reference or knowledge file for a stated
  condition. Read it, return to the calling workflow, and re-evaluate state.
- A loop-back is valid only after state changed, a bounded retry became
  available, or a deterministic fallback produced new evidence.
- The only required owner-confirmation STOP is initial or material
  focused-slice selection in focus. An exact-head owner waiver is optional and
  owner-initiated; never request one merely to bypass correction. Every other
  guard retries, reroutes, defers its exact side effect, or terminates with
  evidence without requesting authority.
- Fast-changing status remains in GitHub. Do not add a tracked handoff or
  current-status duplicate.

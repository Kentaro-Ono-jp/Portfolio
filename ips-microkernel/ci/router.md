# GitHub Actions CI router

<!-- ips-role: router -->
<!-- ips-rule: ci-routing -->

This thin router selects one Proof implementation procedure. The CI Playbook
is a fallible duplicate-preserving correction notebook used to repair test and
proof scripts before remote push. It has no Stage A/B or proved/unproved
classification. Accepted design still defines the behavior to prove. The
canonical entrypoint remains
[`scripts/verify.py`](../../scripts/verify.py), and GitHub Actions remains
authoritative for runtime proof.

Do not preload every procedure, exception, or correction record.

## Select the first matching state

1. **A complete first-pass Behavior and Proof candidate is locally committed
   and ready for an initial or follow-up push:** open
   [pre-push hardening](procedures/preflight.md).
2. **A required local command is missing, mismatched, or taking longer than an
   arbitrary wrapper timeout:** open
   [local rehearsal](procedures/local-rehearsal.md).
3. **The complete candidate qualifies for a Markdown-only Actions skip:** open
   the
   [Markdown-only exception](exceptions/markdown-only.md).
4. **An exact-head Actions run failed:** open
   [failed-run triage](procedures/failure-triage.md).
5. **A feature PR merged and its exact merge workflow completed:** open
   [post-merge CI correction reconciliation](procedures/post-merge-reconcile.md).
6. **A complete candidate is in publication Gate A and changed boundaries must
   select pre-push correction records:** open the
   [CI Playbook selector](knowledge/selector.md).

The order above is precedence. Open one route only. Return here after the
selected procedure changes state; if no condition matches, return to the
[iPS Microkernel work router](../work-router.md).

# GitHub Actions CI router

<!-- ips-role: router -->
<!-- ips-rule: ci-routing -->

This thin router selects one CI procedure. It hardens how an accepted test
runs; it never decides what the test must prove. The canonical entrypoint
remains [`scripts/verify.py`](../../scripts/verify.py), and GitHub Actions
remains authoritative for runtime proof.

Do not preload every procedure, exception, or historical failure record.

## Select the first matching state

1. **A complete implementation and its tests are staged without a commit:**
   open [staged pre-commit hardening](procedures/preflight.md).
2. **A required local command is missing, mismatched, or taking longer than an
   arbitrary wrapper timeout:** open
   [local rehearsal](procedures/local-rehearsal.md).
3. **The complete candidate qualifies for a Markdown-only Actions skip:** open
   the
   [Markdown-only exception](exceptions/markdown-only.md).
4. **An exact-head Actions run failed:** open
   [failed-run triage](procedures/failure-triage.md).
5. **A feature PR merged and its exact merge workflow completed:** open
   [post-merge knowledge reconciliation](procedures/post-merge-reconcile.md).
6. **A known signal or changed boundary needs reusable runner knowledge:** open
   the [CI knowledge selector](knowledge/selector.md).

The order above is precedence. Open one route only. Return here after the
selected procedure changes state; if no condition matches, return to the
[iPS Microkernel work router](../work-router.md).

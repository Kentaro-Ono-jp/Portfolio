# CI knowledge selector

<!-- ips-role: selector -->
<!-- ips-rule: ci-knowledge-selection -->

## Read when

Read this selector only after complete first-pass Proof implementation,
failed-run triage, or post-merge reconciliation identifies a concrete changed
boundary or failure signal.
Select one matching leaf at a time; do not preload the knowledge directory.

## Select a leaf

| Changed boundary or signal | Read only |
|---|---|
| Authenticated principal ownership, token `iss/sub`, synthetic identity-provider fixtures | [Identity proof knowledge](identity.md) |
| Closed request objects, discriminated response unions, generated API types | [API contract proof knowledge](contracts.md) |
| Server-side state crossing independently bundled framework entrypoints | [Framework runtime proof knowledge](framework-runtime.md) |
| Python runtime imports, dependency groups, exact JavaScript framework pins, lockfile advisories | [Dependency knowledge](dependencies.md) |
| Direct execution, working directory, import path, documented command | [Invocation knowledge](invocation.md) |
| PostgreSQL constraints, migrations, transactions, commit or rollback order | [Persistence knowledge](persistence.md) |
| Test-owned records, fault fixtures, stale state, queue ownership | [Runtime isolation knowledge](isolation.md) |
| RabbitMQ or Celery topology, confirms, acknowledgements, worker bootsteps | [Messaging knowledge](messaging.md) |
| Playwright locators, accessible names, framework live regions | [Browser knowledge](browser.md) |
| Health budgets, liveness convergence, retry or recovery orchestration | [Readiness and recovery knowledge](recovery.md) |
| Diagnostics, artifacts, causal failure retention, teardown | [Evidence and teardown knowledge](evidence.md) |

The leaves own admitted reusable proof semantics as well as runner mechanics.
If several boundaries match, read and apply one leaf, return to the caller,
then select the next. If none matches, treat the signal as new or product-
specific; do not force it into a nearby category.

The leaves retain the eleven failed PR runs through PR #12 and the separate
dependency-advisory failure from PR #31. Historical evidence is available for
comparison but is not a default procedure.

PRs [#2](https://github.com/Kentaro-Ono-jp/Portfolio/pull/2),
[#10](https://github.com/Kentaro-Ono-jp/Portfolio/pull/10), and
[#12](https://github.com/Kentaro-Ono-jp/Portfolio/pull/12) had no failed PR
run.

## Return

Return to the procedure that selected this index after one leaf is chosen.

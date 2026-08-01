# CI Playbook selector

<!-- ips-role: selector -->
<!-- ips-rule: ci-knowledge-selection -->

## Read when

Read this selector in publication Gate A after the complete implementation and
Proof candidate exists and before remote push. Select only leaves triggered by
the current candidate, one at a time. Apply relevant correction records to the
current candidate and repair test/proof scripts before `git push`.

Failed-run triage also uses this table after root-cause correction only to
choose the append target. Select the target path without reading or comparing
its prior correction records. The next publication Gate A reads the selected
leaf before the next remote push.

Never preload the Playbook directory. Do not read the CI Playbook after remote
push while waiting for GitHub Actions.

## Select a leaf

| Changed boundary or corrected CI signal | Read or append only |
|---|---|
| Authenticated principal ownership, token `iss/sub`, synthetic identity-provider fixtures | [Identity corrections](identity.md) |
| Closed request objects, discriminated response unions, generated API types | [API contract corrections](contracts.md) |
| Server-side state crossing independently bundled framework entrypoints | [Framework runtime corrections](framework-runtime.md) |
| Python runtime imports, dependency groups, exact JavaScript framework pins, lockfile advisories | [Dependency corrections](dependencies.md) |
| Direct execution, working directory, import path, documented command | [Invocation corrections](invocation.md) |
| PostgreSQL constraints, migrations, transactions, commit or rollback order | [Persistence corrections](persistence.md) |
| Test-owned records, fault fixtures, stale state, queue ownership | [Runtime isolation corrections](isolation.md) |
| RabbitMQ or Celery topology, confirms, acknowledgements, worker bootsteps | [Messaging corrections](messaging.md) |
| Playwright locators, accessible names, framework live regions | [Browser corrections](browser.md) |
| Health budgets, liveness convergence, retry or recovery orchestration | [Readiness and recovery corrections](recovery.md) |
| Diagnostics, artifacts, causal failure retention, teardown | [Evidence and teardown corrections](evidence.md) |

If several boundaries match, read and apply one leaf, return here, then select
the next. If no row matches a corrected CI failure, add one bounded leaf and
one selector row without forcing the signal into a nearby category.

## Correction-record contract

Each entry contains Origin, Trigger, Mistake, and Correction. Origin is
provenance, not Evidence or proof. Duplicate entries, including identical
Mistake and Correction text, are allowed.

After a concrete CI correction, append a new entry to the selected leaf. Do
not scan, compare, reuse, strengthen, merge, or deduplicate earlier entries.
Do not add Evidence, Proof, Status, proved/unproved, promotion, or permanence
fields. Do not wait for successful CI, review, merge, or a dedicated proof
push.

Before remote push, read the selected leaf as fallible operational history.
Apply only records relevant to accepted design and the current candidate, then
repair test/proof scripts in place. A later contradictory or failed result
creates another correction record; it does not change a proof status.

## Return

Return to publication Gate A after applying each triggered leaf before remote
push, or to failed-run triage after selecting the append target.

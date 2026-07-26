# Runtime isolation knowledge

<!-- aios-role: knowledge -->
<!-- aios-rule: ci-knowledge-isolation -->

## Read when

Read this file when a verifier uses runtime fixtures, fault records, shared
queues, or state that may survive or race another actor.

## Durable rule

Select records by deterministic identities owned by the check, not a global
row that merely matches. Quiesce competing consumers before purging or
asserting queue ownership. Clean owned data before the check and again in
`finally`.

## Historical evidence

PR #6 [run 29666718552](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29666718552)
could not create a simulated crashed-dispatcher lease because runtime proof
shared stale database state. Fix
[`58be144`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/58be144ae074da5616f6907c563a2007793aaba6)
and [run 29666913637](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29666913637)
established deterministic ownership and cleanup. Guards remain in
[`test_integration.py`](../../../apps/api/tests/test_integration.py) and
[`verify_outbox_runtime.py`](../../../scripts/verify_outbox_runtime.py).

## Return

Return to the calling CI procedure after proving owned state and isolation.

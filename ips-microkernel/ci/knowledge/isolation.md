# Runtime isolation knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-isolation -->

## Read when

Read this file when a verifier uses runtime fixtures, fault records, shared
queues, or state that may survive or race another actor.

## Durable rule

Select records by deterministic identities owned by the check, not a global
row that merely matches. Quiesce competing consumers before purging or
asserting queue ownership. Clean owned data before the check and again in
`finally`.

## Stateful test doubles

### Preserve production failure precedence

- **Phase:** `pre-CI`
- **Trigger:** A stateful test double represents a production repository or
  adapter with more than one failure condition for the same operation.
- **Mistake:** The double checks the right failures in a different order, so
  API tests publish a failure model the production adapter does not preserve.
- **Check:** Does the double return the same first failure as production for
  every overlapping condition exercised by the feature?
- **Guard:** Use one request that triggers two conditions against both the
  double-backed boundary and production repository; require identical failure
  precedence, then prove each later condition with the earlier one satisfied.
- **Evidence:** PR #61
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5150104462).

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

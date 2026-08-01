# CI Playbook: identity corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-identity -->

## Read when

Before remote push, read this leaf when the complete candidate changes
authenticated identity, token claims, ownership expectations, or
synthetic-provider fixtures.

## Correction records

### Replace legacy ownership expectations

- **Origin:** PR #57
  [run 30627309389](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30627309389)
- **Trigger:** Runtime checks move a resource from anonymous or legacy-system
  ownership to authenticated principal ownership.
- **Mistake:** Assertions and fixtures still expected the anonymous-era or
  legacy owner.
- **Correction:** Use the stable authenticated principal in setup, queries, and
  assertions; prove it differs from the legacy principal through the
  production-shaped runtime path.

### Derive exact validated token identity

- **Origin:** PR #57
  [run 30627826543](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30627826543)
- **Trigger:** A synthetic identity provider supplies tokens used by runtime
  checks.
- **Mistake:** The test treated a human-readable fixture or provider user ID as
  OAuth `sub`, or guessed `iss`.
- **Correction:** Derive expected `iss` and `sub` through the production token
  validation path and compare exact claims with persisted ownership evidence.

### Cross ownership hiding with replay classification

- **Origin:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788)
- **Trigger:** An authenticated mutation combines ownership hiding with an
  idempotency key or another target-bound replay mechanism.
- **Mistake:** Ownership and replay were tested independently, leaving an
  uncovered precedence path for hidden targets.
- **Correction:** In every affected adapter, cross hidden and owned targets
  with reused and fresh keys; require identical not-found results and zero
  mutation for hidden targets while retaining owned-target replay coverage.

## Return

Return to publication Gate A after repairing only the triggered identity
test/proof scripts.

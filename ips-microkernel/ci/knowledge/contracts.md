# CI Playbook: API contract corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-contracts -->

## Read when

Before remote push, read this leaf when the complete candidate changes closed
API request objects, discriminated response unions, request constraints, or
generated API types. Use applicable records to repair test/proof scripts.

## Correction records

### Reject extras through the runtime boundary

- **Origin:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788)
- **Trigger:** A request schema is closed with `additionalProperties: false`.
- **Mistake:** Schema validation rejected extra fields while the runtime model
  silently dropped them.
- **Correction:** Exercise a contract-valid request plus one actor-looking
  extra property through the production boundary; require canonical validation
  failure, zero protected service calls, and no state mutation.

### Cover reachable and unreachable union states

- **Origin:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788)
- **Trigger:** A discriminated response union has relational invariants beyond
  field presence and primitive types.
- **Mistake:** Positive fixtures covered each discriminator while impossible
  discriminator-and-field combinations remained valid or serializable.
- **Correction:** Keep positive fixtures for every reachable variant, inverse
  negative fixtures for each violated relation, runtime serializer checks, and
  regenerated types from the validated contract.

### Match parameter constraints at the production boundary

- **Origin:** PR #61
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5150104462)
- **Trigger:** A canonical path, query, header, or cookie parameter declares a
  pattern, range, format, or enum constraint.
- **Mistake:** Schema lint covered the constraint while runtime transport
  accepted a broader value and routed it into domain failure handling.
- **Correction:** Exercise one contract-invalid parameter on an otherwise-valid
  request through the production parser; require canonical validation failure,
  zero protected calls, and no state mutation.

## Return

Return to publication Gate A after repairing only test/proof scripts triggered
by the complete candidate.

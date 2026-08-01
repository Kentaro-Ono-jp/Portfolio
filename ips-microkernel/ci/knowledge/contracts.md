# API contract proof knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-contracts -->

## Read when

Read this file after complete Proof implementation changes closed API request
objects, discriminated response unions, or generated API types.

## Entries

### Reject extras through the runtime boundary

- **Phase:** `pre-CI`
- **Trigger:** A request schema is closed with `additionalProperties: false`.
- **Mistake:** Schema validation rejects extra fields while the runtime model
  silently drops them, so implementation and contract accept different input.
- **Check:** Does a contract-valid request plus one extra property fail at the
  production request-validation boundary as well as schema validation?
- **Guard:** Use an actor- or authority-looking extra property, require the
  canonical validation response, and prove that no protected service call or
  state mutation occurs.
- **Evidence:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788).

### Prove reachable and unreachable union states

- **Phase:** `pre-CI`
- **Trigger:** A discriminated response union has relational invariants beyond
  field presence and primitive types.
- **Mistake:** Positive fixtures validate each discriminator, but impossible
  discriminator-and-field combinations remain contract-valid or serializable.
- **Check:** Are every reachable variant and the inverse impossible states
  exercised against the canonical schema and runtime serializer?
- **Guard:** Keep positive fixtures for every variant, negative fixtures for
  each violated relation, and regenerate types from the validated contract.
- **Evidence:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788).

## Return

Return to the calling CI procedure after applying only the triggered entries.

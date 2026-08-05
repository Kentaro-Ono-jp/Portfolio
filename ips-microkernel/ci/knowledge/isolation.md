# CI Playbook: runtime isolation corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-isolation -->

## Read when

Before remote push, read this leaf when a verifier uses runtime fixtures,
fault records, shared queues, or state that may survive or race another actor.

## Correction records

### Own and clean runtime records deterministically

- **Origin:** PR #6
  [run 29666718552](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29666718552)
- **Trigger:** Runtime proof creates fault records, leases, or queue state that
  another actor or earlier run may also own.
- **Mistake:** A check selected a global matching row and shared stale database
  state, preventing deterministic fault setup.
- **Correction:** Select records by identities owned by the check, quiesce
  competing consumers, clean owned data before execution and again in
  `finally`, and avoid global-row assertions.

### Preserve production failure precedence in doubles

- **Origin:** PR #61
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5150104462)
- **Trigger:** A stateful test double represents a production adapter with more
  than one failure condition for the same operation.
- **Mistake:** The double checked correct failures in a different order and
  published a different first failure from production.
- **Correction:** Trigger overlapping conditions against both double and
  production adapter, require the same first failure as production, then cover
  each later condition with the earlier one satisfied.

### Construct representation faults independently of host newline translation

- **Origin:** PR #82
  [run 31022587681](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31022587681)
- **Trigger:** A test fixture must differ byte-for-byte from a canonical JSON
  representation on every supported runner operating system.
- **Mistake:** A noncanonical fixture relied on Windows newline translation and
  became canonical when written on Linux.
- **Correction:** Write an explicitly compact JSON byte representation so the
  intended representation fault is deterministic across operating systems.

## Return

Return to publication Gate A after repairing only the triggered isolation
test/proof scripts.

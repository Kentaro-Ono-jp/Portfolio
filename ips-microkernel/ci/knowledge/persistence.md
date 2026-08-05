# CI Playbook: persistence corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-persistence -->

## Read when

Before remote push, read this leaf for migrations, PostgreSQL constraints,
transaction order, flush behavior, or commit and rollback boundaries.

## Correction records

### Flush document dependencies before dependent rows

- **Origin:** PR #4
  [run 29639776329](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639776329)
- **Trigger:** One transaction inserts a document and rows with foreign keys to
  it.
- **Mistake:** ORM insertion order was assumed to satisfy a real PostgreSQL
  foreign key.
- **Correction:** Flush dependency rows explicitly before dependent inserts,
  add regression coverage for ordering, and exercise the real PostgreSQL path
  and server-specific types.

### Flush job and outbox dependencies before dependents

- **Origin:** PR #4
  [run 29641893290](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29641893290)
- **Trigger:** A later transaction inserts job and outbox rows whose foreign
  keys depend on other new rows.
- **Mistake:** The same ORM-order assumption recurred for a different dependent
  graph.
- **Correction:** Make job and outbox dependency flush order explicit and
  cover the concrete PostgreSQL transaction with regression tests.

### Keep populated-schema verifier heads aligned with Alembic

- **Origin:** PR #82
  [run 31023188296](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31023188296)
- **Trigger:** A new migration extends the current Alembic head while multiple
  populated-schema verifiers upgrade through that head.
- **Mistake:** One verifier retained the preceding revision and treated a
  successful upgrade to the new real head as failure.
- **Correction:** Update every populated-schema verifier's declared head and
  statically require those declarations to equal Alembic's current head.

## Return

Return to publication Gate A after repairing only the triggered persistence
test/proof scripts.

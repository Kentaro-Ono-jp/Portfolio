# Persistence knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-persistence -->

## Read when

Read this file for migrations, PostgreSQL constraints, transaction order,
flush behavior, or commit and rollback boundaries.

## Durable rule

Do not treat ORM insertion order as a database contract. Flush dependency rows
explicitly where ordering is required, prove that order with regression tests,
and exercise the real PostgreSQL path and server-specific types.

## Historical evidence

PR #4 failed in
[run 29639776329](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639776329)
and again after review in
[run 29641893290](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29641893290)
with a real foreign-key violation. Fixes
[`2cecec2`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/2cecec26e82e3034ffbae3f73f6f4db29bfc2425)
and
[`05b3532`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/05b35322f2bf07a4757eaf0791e5a9c0e5d6ab7a)
made document, job, and outbox ordering explicit; successful runs
[29639908626](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639908626)
and
[29642127264](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29642127264)
closed the chain. Guards remain in
[`persistence.py`](../../../apps/api/src/reactorfront_api/persistence.py) and
[`test_persistence.py`](../../../apps/api/tests/test_persistence.py).

## Return

Return to the calling CI procedure with the real-database ordering proved.

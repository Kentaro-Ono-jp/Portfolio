# Invocation portability knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-invocation -->

## Read when

Read this file when a directly executed script, documented working directory,
or import path differs between local use and GitHub Actions.

## Durable rule

Resolve imports using the exact documented command and working directory
without an unrecorded `PYTHONPATH`. Exercise that same direct script path
through the canonical verifier and lint every verification helper.

## Historical evidence

PR #8 [run 29672537036](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29672537036)
could not import `scripts.pdf_fixture` because direct execution placed the
scripts directory, not an assumed repository package root, on the import path.
Fix [`549d088`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/549d0889f03f3d7a471c31263fd5cb60656299f0)
advanced the chain, which closed at
[run 29674130187](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29674130187).
The canonical guard is
[`verify_ml_runtime.py`](../../../scripts/verify_ml_runtime.py) executed by
[`verify.py`](../../../scripts/verify.py).

## Return

Return to the calling CI procedure with the exact invocation made portable.

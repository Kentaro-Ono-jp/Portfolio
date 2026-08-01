# CI Playbook: invocation corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-invocation -->

## Read when

Before remote push, read this leaf when a directly executed script, documented
working directory, or import path differs between local use and GitHub
Actions.

## Correction records

### Make direct script imports portable

- **Origin:** PR #8
  [run 29672537036](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29672537036)
- **Trigger:** A verifier is executed directly by its documented command and
  working directory.
- **Mistake:** Direct execution could not import `scripts.pdf_fixture` because
  the script directory, not an assumed repository package root, was on the
  import path.
- **Correction:** Resolve imports under the exact documented invocation without
  an unrecorded `PYTHONPATH`, exercise the direct path through
  [`verify.py`](../../../scripts/verify.py), and lint every verification
  helper.

## Return

Return to publication Gate A after repairing the triggered invocation scripts.

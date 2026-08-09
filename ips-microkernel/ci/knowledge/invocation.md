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

### Supply complete fail-closed local-service configuration to CI

- **Origin:** PR #104
  [run 31289122644](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31289122644)
- **Trigger:** GitHub Actions overrides a local service endpoint consumed by settings validation during static and runtime verification.
- **Mistake:** The workflow supplied only the MinIO endpoint, so API and ML received partial local S3 configuration after the settings boundary began rejecting incomplete endpoint/credential tuples.
- **Correction:** Supply the complete bounded synthetic MinIO endpoint and credential tuple for every consumer, isolate default/AWS-mode unit settings from workflow overrides, and enforce that workflow invocation contract with an executable repository test.

### Resolve documented repository-relative measurement paths

- **Origin:** PR #104
  [run 31289454252](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/31289454252)
- **Trigger:** A directly executed verifier accepts repository-relative input and output paths and records a repository-relative evidence identity.
- **Mistake:** The verifier compared an unresolved relative configuration path directly with the absolute repository root after the measured workload succeeded, raising an exception only in the full command path.
- **Correction:** Resolve input and output paths from the repository root before use, reject paths outside that root, and directly test the documented relative invocation boundary.

## Return

Return to publication Gate A after repairing the triggered invocation scripts.

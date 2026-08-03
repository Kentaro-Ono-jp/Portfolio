# CI Playbook: evidence and teardown corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-evidence -->

## Read when

Before remote push, read this leaf when the complete candidate changes
diagnostics, artifacts, leakage scanning, failure ordering, or teardown.

## Correction records

### Preserve the first causal failure

- **Origin:** Existing CI diagnostics correction record
- **Trigger:** Diagnostics, artifact upload, or cleanup can fail after a causal
  test or service error.
- **Mistake:** Teardown noise or evidence collection replaced the first causal
  failure.
- **Correction:** Preserve the first failure, run sanitized evidence collection
  and scoped teardown unconditionally, and report later failures without
  overwriting the cause.

### Keep artifact identity rerun-safe

- **Origin:** Existing GitHub Actions artifact correction record
- **Trigger:** Failed-jobs-only or full reruns may upload the same logical
  artifact.
- **Mistake:** Artifact identity changed across partial reruns or a full rerun
  collided without explicit overwrite behavior.
- **Correction:** Keep cross-job artifact identity stable and use explicit
  overwrite semantics when a full rerun regenerates the same artifact.

### Scope teardown to owned resources

- **Origin:** Existing portfolio teardown correction record
- **Trigger:** CI creates Docker Compose or other ephemeral resources.
- **Mistake:** Cleanup could target resources outside the portfolio project or
  assume local execution inherited ephemeral-runner volume removal.
- **Correction:** Target only the `reactorfront-portfolio` project and owned
  ephemeral resources; never run Docker prune or unscoped cleanup, and express
  local cleanup separately.

### Exercise changed fail-closed boundaries before coverage publication

- **Origin:** PR #78 external Codecov patch check
- **Trigger:** Exact-head verification succeeded, but the later patch-coverage
  check reported 90.15% against the repository target of 91.45%.
- **Mistake:** Focused mutation tests left changed manifest-validation and
  evaluator failure branches unexecuted, including finite confidence values
  outside the declared zero-to-one range.
- **Correction:** Add executable mutations for the changed fail-closed
  branches and reject out-of-range confidence before publishing measured
  coverage for the next exact head.

## Return

Return to publication Gate A after repairing the triggered evidence and
teardown scripts.

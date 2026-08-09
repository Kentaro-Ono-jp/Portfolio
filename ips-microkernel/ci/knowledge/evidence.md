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

### Cover runtime promotion error translation

- **Origin:** PR #86 `codecov/patch` external check.
- **Trigger:** Exact-head Actions published complete measured coverage, but the required patch-coverage check reported `91.36%` against a `91.45%` target.
- **Mistake:** Invalid promotion evidence was translated to the stable runtime-lineage failure without a focused test executing that changed error path.
- **Correction:** Exercise runtime construction with rejected promotion evidence and require the exact `RuntimeLineageError` plus preserved `PromotionError` cause.

### Exercise generated policy failure boundaries

- **Origin:** PR #107 pre-push Gate A after
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230145388).
- **Trigger:** AWS-free proof adds generated IAM policy quotas, delegated-policy
  immutability, or trust-metadata connectivity guards.
- **Mistake:** The passing candidate reported compliant values but did not
  execute the new rejection branches, and its trust-policy verifier used a
  higher limit than the Terraform precondition.
- **Correction:** Canonicalize and exercise one over-limit mutation per policy
  class plus delegated mutation and disconnected-event mutations through the
  production structure verifier, requiring the exact fail-closed class before
  publishing evidence.

### Exercise ownership tag-key ceilings

- **Origin:** PR #107 follow-up Gate A after re-review correction
- **Trigger:** AWS-free policy proof adds an exact `aws:TagKeys` allowlist to a
  generated identity policy.
- **Mistake:** Positive and cross-environment tag cases did not execute the
  evaluator branch that rejects an otherwise exact request with an additional
  undeclared tag key.
- **Correction:** Add one canonical tag request containing the complete allowed
  ownership tuple plus one extra key, and require the effective policy to deny
  it before publishing evidence.

## Return

Return to publication Gate A after repairing the triggered evidence and
teardown scripts.

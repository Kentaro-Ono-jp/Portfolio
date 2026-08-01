# CI Playbook: dependency corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-dependencies -->

## Read when

Before remote push, read this leaf for Python runtime-import boundaries,
dependency groups, pinned JavaScript frameworks, lockfiles, or newly published
advisories.

## Correction records

### Isolate type-only runtime imports

- **Origin:** PR #4
  [run 29639639004](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639639004)
- **Trigger:** Production code imports types supplied only by a development or
  type-checking dependency group.
- **Mistake:** `mypy_boto3_s3` leaked into a production runtime import.
- **Correction:** Move the import behind `TYPE_CHECKING`, keep runtime modules
  independent of type-only packages, and smoke-import the installed
  application inside its production image.

### Re-audit the exact dependency candidate

- **Origin:** PR #31
  [run 30155542598](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30155542598)
- **Trigger:** A candidate retains or changes a frozen production dependency
  graph.
- **Mistake:** An earlier successful audit was treated as permanent even after
  a new advisory covered an unchanged exact pin.
- **Correction:** Run the production audit for every exact candidate; update
  affected direct pins and aligned tooling to a patched release, constrain only
  vulnerable transitive edges, regenerate the lockfile, and remove stale
  copies of old versions.

## Return

Return to publication Gate A after repairing only the triggered dependency
test/proof scripts and manifests.

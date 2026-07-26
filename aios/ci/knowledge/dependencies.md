# Dependency knowledge

<!-- aios-role: knowledge -->
<!-- aios-rule: ci-knowledge-dependencies -->

## Read when

Read this file for Python runtime-import boundaries, dependency groups, pinned
JavaScript frameworks, lockfiles, or newly published advisories.

## Durable rules

- A runtime module must not import a development-only or type-only package.
  Isolate type imports with `TYPE_CHECKING` and smoke-import the installed
  application inside its production image.
- A successful earlier audit does not permanently validate an unchanged frozen
  dependency graph. Rerun production audits for every exact candidate.
- When an advisory applies, update the affected direct exact pin and aligned
  framework tooling to the first patched release. Constrain only an affected
  transitive edge when its upstream range still resolves vulnerably.
- Regenerate the lockfile and search the repository for stale copies of the old
  version.

The canonical guards are production image imports,
`pnpm audit --prod --audit-level moderate`, frozen installs, exact manifests,
and narrow lockfile resolutions.

## Historical evidence

- PR #4 [run 29639639004](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639639004)
  exposed `mypy_boto3_s3` as a leaked type-only runtime import. Fix
  [`df47d81`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/df47d81f2f932132801285c2bab3dce9315fffb0)
  and [run 29639908626](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639908626)
  closed the signal. Guards remain in
  [`storage.py`](../../../apps/api/src/reactorfront_api/storage.py) and the
  [API Dockerfile](../../../infra/docker/api/Dockerfile).
- PR #31 [run 30155542598](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30155542598)
  rejected an unchanged Next.js pin after new advisories. Correction
  [`bd87ca6`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/bd87ca6f3a0032fdd287c309d6baa55f20b6f5d2)
  and [run 30155965735](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30155965735)
  established exact-candidate re-audit and narrow transitive correction.

## Return

Return to staged preflight, failed-run triage, or post-merge reconciliation
with only the applicable rule and evidence.

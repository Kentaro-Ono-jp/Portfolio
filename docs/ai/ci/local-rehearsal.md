# Local rehearsal boundaries

<!-- docforai-role: procedure -->
<!-- docforai-rule: ci-local-rehearsal -->

## Read when

Read this file when a selected local check is blocked by a missing command,
host-version mismatch, or orchestration timeout.

## Procedure

- Resolve only tools required by the selected plan.
- The static-only verifier resolves `pnpm` and `uv` but does not resolve or
  invoke the Docker CLI.
- Compare Node and Python with `.node-version` and `.python-version`; use the
  `uv` version pinned by the workflow.
- Use the repository's
  [local tool authorization](../reference/local-tools.md) when installation is
  required, then return here.
- Do not impose an arbitrary process timeout on
  `scripts/verify.py --static-only`. Yield or poll without terminating it.
- External timeout termination is not verification evidence.
- Disclose a local runtime mismatch. GitHub Actions on pinned versions remains
  authoritative.

These conditions are local orchestration, not additional failed Actions runs
in the historical knowledge base.

## Fallback

Do not request elevated privileges, persistent background services, Docker
mutation, credentials, or paid tools. Use a user-scoped or temporary compatible
runtime when available. Otherwise route environment-dependent proof to GitHub
Actions and return the exact local limitation to the caller.

## Return

Return to staged preflight or the calling workflow after the exact tool version
and check outcome are known.

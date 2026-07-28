# Local development tool authorization

<!-- ips-role: reference -->
<!-- ips-rule: local-tool-authorization -->

## Read when

Read this file only when an ordinary local development or review tool is
missing, incompatible, or likely to materially reduce the accepted work.

## Standing authorization

Implementation and independent review agents may install ordinary local tools
and runtimes during implementation, publication, correction, review, and
post-merge evidence work without a per-install pause.

- On an owner-managed persistent workstation, prefer a persistent user-scoped
  installation.
- Use the repository-pinned version when one exists; otherwise use a compatible
  stable version from an official package manager or source.
- A successful installation and basic version check are sufficient unless a
  stronger repository or security instruction applies.
- After a verified replacement, a superseded user-scoped version of the same
  tool may be removed only when no active repository process uses its old path.
- Use a unique system temporary location when the host must remain unchanged,
  persistent installation is unavailable, or versions conflict. Remove only
  that verified location afterward.

Do not request elevated privileges, reboots, drivers, persistent background
services, credentials, paid licenses, Docker runtime mutation, or unrelated
upgrades. Prefer a compatible user-scoped or temporary tool. When none exists,
route Docker-backed or environment-dependent proof to GitHub Actions and
record any remaining local limitation.

## Return

Report the installed or selected version, fallback, and limitation, then return
to the calling workflow.

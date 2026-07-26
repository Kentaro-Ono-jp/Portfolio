# Independent review setup

<!-- docforai-role: procedure -->
<!-- docforai-rule: review-setup -->

## Read when

Read this file first after the review router validates all required inputs.

## Procedure

1. Read the governing tracking Issue, focused Issue, and complete PR
   description.
2. Use the delivery and ADR indexes to select only the governing specification
   sections and decisions implicated by the focused scope. Do not read all
   accepted records by default.
3. For re-review, read the previous verdict and implementation response.
4. Resolve the live PR head and require it to equal the expected full SHA.
   Require the PR description's current-review head to equal the same SHA and
   classify workflow evidence accurately as exact-head, preceding, superseded,
   or intentionally absent.
5. Create a unique, short direct child of the platform temporary root.
6. Shallow-clone only the exact PR head with `--depth 1` and `--no-tags`.
7. Require `git rev-parse HEAD` to equal the expected full SHA. Never reuse or
   modify the canonical workspace.

Ordinary missing review tools may use the
[local tool authorization](../reference/local-tools.md); return here after the
tool version is confirmed.

## Setup guard

Do not approve or inspect a substitute head when inputs conflict, the head
moved, the PR description is stale, required live evidence is unavailable, or
the isolated clone cannot be proved exact.

## Next

With an exact isolated clone and current evidence, open
[review inspection](inspect.md).

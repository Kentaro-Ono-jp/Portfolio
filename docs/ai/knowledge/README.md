# Governance knowledge selector

<!-- docforai-role: router -->
<!-- docforai-rule: governance-knowledge-selection -->

## Read when

Read this selector only after governance reconciliation identifies one
concrete reusable process or review signal. It is not an append-only incident
ledger. Select one canonical target, return to the caller, and do not preload
the other targets.

## Select one target

| Signal | Canonical target |
|---|---|
| Actor, permission, confirmation, or mutation boundary | [Authority reference](../reference/authority.md) |
| Dirty, stale, moved, contradictory, or unknown-writer recovery | [Live-state reference](../reference/live-state.md) |
| Local command, installation, privilege, or environment fallback | [Local-tools reference](../reference/local-tools.md) |
| Secret, private context, machine path, fixture, or public content | [Public-safety reference](../reference/public-safety.md) |
| Focused or umbrella Issue evidence and completion proof | [Evidence reference](../reference/evidence.md) |
| Focused-slice selection or material redefinition | [Focus workflow](../workflows/focus.md) |
| Implementation, verification, or staged-candidate preparation | [Implementation workflow](../workflows/implement.md) |
| Commit, push, Draft PR, or exact-head evidence | [Publication workflow](../workflows/publish.md) |
| Actionable-review correction and re-review loop | [Correction workflow](../workflows/correct.md) |
| Ready or exact-head merge guard | [Merge workflow](../workflows/merge.md) |
| Main proof, Issue evidence, branch, or task-owned cleanup | [Reconciliation workflow](../workflows/reconcile.md) |
| Independent clone and exact-head setup | [Review setup](../review/setup.md) |
| Independent full-diff and proof inspection | [Review inspection](../review/inspect.md) |
| One-comment verdict content or publication | [Review verdict](../review/verdict.md) |
| Independent temporary-data cleanup | [Review cleanup](../review/cleanup.md) |
| CI runner, verification, or Actions failure | [CI router](../../../.github/workflows/CI_PLAYBOOK.md) |
| Product or structural decision | [ADR index](../../adr/README.md) through the focus workflow |
| Delivery contract, acceptance, or completion evidence | [Delivery index](../../delivery/README.md) through the focus workflow |

If no row owns the signal, return it as an unclassified candidate. Do not force
it into a nearby target or add a duplicate general ledger.

## Promotion contract

Compare the candidate with the selected canonical rule and its executable
guards. Prefer a regression check over prose alone.

A new reusable process rule requires an accepted focused governance Issue and
an independently reviewed PR before guidance mutation. When the current
focused governance PR already proves that exact accepted update, record it as
satisfied without creating a recursive empty Issue.

## Return

Return the selected target, classification, existing-rule comparison, and
promotion outcome to governance reconciliation.

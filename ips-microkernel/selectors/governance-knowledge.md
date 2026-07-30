# Governance knowledge selector

<!-- ips-role: selector -->
<!-- ips-rule: governance-knowledge-selection -->

## Read when

Read this selector only after governance reconciliation identifies one
concrete reusable process or review signal. It is not an append-only incident
ledger. Select one canonical target, return to the caller, and do not preload
the other targets.

## Select one target

Rows are ordered precedence. Classify one atomic root-cause signal with the
first matching key. If one observation spans several keys, split it into
atomic candidates before selection; never assign one candidate to two targets.

| Signal key | Signal | Canonical target |
|---|---|---|
| `actor-authority` | Actor, permission, confirmation, or mutation boundary | [Authority reference](../references/authority.md) |
| `live-state` | Dirty, stale, moved, contradictory, or unknown-writer recovery | [Live-state reference](../references/live-state.md) |
| `local-tools` | Local command, installation, privilege, or environment fallback | [Local-tools reference](../references/local-tools.md) |
| `public-safety` | Secret, private context, machine path, fixture, or public content | [Public-safety reference](../references/public-safety.md) |
| `issue-evidence` | Checklist criterion mapping, completion-evidence content, or umbrella-gate proof | [Evidence reference](../references/evidence.md) |
| `focus` | Focused-slice selection or material redefinition | [Focus workflow](../procedures/focus.md) |
| `implementation` | Implementation, verification, or staged-candidate preparation | [Implementation workflow](../procedures/implement.md) |
| `publication` | Commit, push, Draft PR, or exact-head evidence publication | [Publication workflow](../procedures/publish.md) |
| `adjudication` | Review-finding disposition, human-scale lenses, or adjudicated-RC routing | [Review adjudication](../procedures/adjudicate.md) |
| `correction` | Actionable-review correction and re-review loop | [Correction workflow](../procedures/correct.md) |
| `merge` | Ready or exact-head merge guard | [Merge workflow](../procedures/merge.md) |
| `reconciliation` | Post-merge sequencing, main fast-forward, branch deletion, or task-owned cleanup | [Reconciliation workflow](../procedures/reconcile.md) |
| `review-setup` | Independent clone and exact-head setup | [Review setup](../review/setup.md) |
| `review-inspection` | Independent full-diff and proof inspection | [Review inspection](../review/inspect.md) |
| `review-verdict` | One-comment verdict content or publication | [Review verdict](../review/verdict.md) |
| `review-cleanup` | Independent temporary-data cleanup | [Review cleanup](../review/cleanup.md) |
| `ci` | CI runner, verification, or Actions failure | [CI router](../ci/router.md) |
| `architecture` | Product or structural decision | [ADR index](../adr/index.md) |
| `delivery` | Delivery contract, acceptance, or completion evidence | [Delivery index](../delivery/index.md) |

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

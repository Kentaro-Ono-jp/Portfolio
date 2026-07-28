# Focus workflow

<!-- ips-role: procedure -->
<!-- ips-rule: focus-workflow -->

## Read when

Read this file when no accepted focused scope or exact branch exists, or when a
material scope change requires a new slice decision.

## Inputs

- owner-requested outcome
- repository identity
- known focused Issue or PR, if any

## Procedure

1. Use the [delivery index](../delivery/index.md) to select the governing
   specification and tracking Issue. Read only relevant specification sections.
2. Use the [ADR index](../adr/index.md) to select only decisions implicated
   by the requested boundary.
3. Read the nearest area README only after affected files or deployable areas
   are known.
4. Run the bounded checks in [live state](../references/live-state.md), then
   return here.
5. Propose one smallest coherent slice with outcome, scope, non-targets,
   failure model, acceptance criteria, and proof plan. Present materially
   different alternatives separately instead of silently combining them.
6. After the owner selects that slice, create or update one focused Issue with
   the accepted boundary.
7. Keep material architecture or delivery-contract changes aligned with a new
   ADR or specification update in the same work.
8. After a clean status and exact fetched base are proved, create the focused
   branch from `origin/main`.

Do not absorb an adjacent application boundary. Offer it as a later slice.

## Owner-confirmation STOP

Stop only when the initial slice has not been selected or a material
redefinition presents more than one materially different outcome. Ask the
owner to select the proposed slice boundary.

Dirty state, a moved base, unavailable GitHub state, or contradictory live
evidence uses live-state recovery first. Governing-specification ambiguity
requires a decision here only when it would materially change the slice.

## Next

- For governance or other public documentation, read
  [public safety](../references/public-safety.md), return here, then continue.
- When the selected focused Issue and exact branch exist, open
  [implement and verify](implement.md).

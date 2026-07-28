# ADR-0012: Name AIOS nodes by runtime role

- Status: Superseded by ADR-0013
- Date: 2026-07-26
- Deciders: ReactorFront
- Related: ADR-0008, ADR-0009, ADR-0010, ADR-0011, Issue #40

## Context

ADR-0008 changed repository-owned AI guidance from one large manual into a
progressively disclosed routing graph. ADR-0009 through ADR-0011 then added
reviewed knowledge reconciliation, lossless review-candidate capture, and
deterministic shallow-review diff proof.

The resulting system has become a development operating system rather than a
collection of ordinary documentation. Its legacy `DocForAI` name and several
filesystem names no longer describe that behavior. In particular, runtime
routers and selectors used `README.md` or historical feature names, knowledge
selection looked like a generic index, and the CI router lived beside workflow
definitions even though it governed the wider repository lifecycle.

Names that conceal runtime roles make cold-start routing harder to inspect and
allow a file's responsibility to drift without a visible structural change.
Keeping the complete system under a generic documentation directory also
understates that ADRs, delivery contracts, procedures, review, and CI knowledge
form one governed operating system.

## Decision

### Name the system AIOS

The complete top-level `docs/` tree moves to `aios/`. ADR, architecture,
delivery, runtime guidance, review, and CI governance are all AIOS assets.
There is no compatibility directory or duplicate live route at the former
location.

The former `docs/ai/` runtime subtree is flattened into role-expressive paths
under `aios/`. The three entry routers are:

- `aios/work-router.md`
- `aios/review/router.md`
- `aios/ci/router.md`

### Declare six runtime roles

Every AIOS runtime node declares exactly one machine-readable role:

- `router`: selects the next state or subsystem
- `selector`: maps one classified signal to one canonical destination
- `procedure`: performs one bounded lifecycle operation
- `reference`: supplies a durable boundary or invariant on demand
- `knowledge`: retains one reusable CI decision domain
- `exception`: governs a narrowly qualified departure from the normal route

Markers use the `aios-role` and `aios-rule` namespaces. Selector and exception
roles are distinct from routers and procedures so their narrower semantics
remain machine-visible.

### Make paths prove roles

Runtime filenames and directories encode their role. Routers use
`work-router.md` or `router.md`; selectors use `selectors/` or `selector.md`;
procedures use `procedures/` or the bounded review procedure set; references,
knowledge, and exceptions live in their corresponding plural directories.

The documentation checker derives a role from each runtime path, compares it
with the declared marker and exact inventory, and rejects disagreement,
unrouted additions, runtime `README.md` files, legacy marker namespaces, or
restored legacy live paths.

### Call indexes indexes

ADR, architecture, and delivery directory summaries use `index.md`. They are
human and design indexes, not runtime routers, and therefore do not carry a
runtime role marker.

### Preserve accepted history

Accepted ADR prose remains immutable evidence. Earlier ADRs may name the paths
that existed when those decisions were accepted. Those historical statements
are not live routes and are not rewritten. All current entrypoints, links,
tests, and enforcement use AIOS paths, while this ADR records the transition.

## Consequences

### Positive

- The top-level name now matches the system's operating responsibility.
- A cold reader can infer a node's purpose before opening it.
- Selectors and exceptions cannot silently masquerade as broader node types.
- Runtime role drift and legacy path restoration fail in automated checks.
- ADR, delivery, review, CI, and knowledge assets have one coherent namespace.

### Costs

- Existing links and local habits that use the former paths must change.
- The migration touches many files even though runtime behavior is preserved.
- Future runtime additions must choose a supported role and update the exact
  routed inventory through focused review.

## Rejected alternatives

- Keep `docs/` and rename only the former AI guidance subtree.
- Add `aios/` beside `docs/` and split the operating system across two roots.
- Preserve compatibility copies or redirects at legacy live paths.
- Continue using `README.md` for runtime selectors and routers.
- Infer every role from prose without machine-readable markers.

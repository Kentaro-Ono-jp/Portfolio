# ADR-0013: Name the document governance architecture iPS Microkernel

- Status: Accepted
- Date: 2026-07-28
- Deciders: ReactorFront
- Supersedes: ADR-0012
- Related: ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0012, Issue #42

## Context

ADR-0012 named the complete repository-owned development operating system
AIOS, moved its governed assets into one top-level tree, and made six runtime
roles structurally visible. That change accurately captured the system's
operating responsibility, but the AIOS name remained broader than the
mechanism that made the architecture distinctive and collided with existing
concepts and service names.

The system's defining behavior is intentional non-loading. A thin entrypoint
and work router select one state transition; detailed procedures, durable
references, reusable knowledge, and qualified exceptions remain unloaded until
a matching signal requires them. Roles, paths, links, transitions, evidence,
and automated inspection make this more than Markdown organization.

The public product and the governance architecture also need distinct
identities. The repository root README presents the Document Intelligence and
Human Review Platform. A longer architecture origin story belongs inside the
governance namespace, but loading that story into normal agent context would
violate the architecture it explains.

## Decision

### Name the architecture iPS Microkernel

The canonical name is **iPS Microkernel**, expanded as:

> **intentional Progressive-disclosure System Microkernel**

The words define the contract:

- `intentional`: not loading unrelated information is an explicit design
  decision rather than missing context;
- `Progressive-disclosure`: the current state reveals only the next required
  router, procedure, reference, knowledge module, or exception;
- `System`: roles, routes, transitions, authority, evidence, and inspection
  form a governed runtime;
- `Microkernel`: startup retains a thin dispatch layer while detailed services
  remain outside it until selected.

The biological language of reprogramming, differentiation, dormancy, and
expression communicates the architecture to humans. Runtime contracts use the
inspectable terms route, select, load, activate, transition, return, prove, and
validate. The name does not claim literal operating-system process isolation or
biological behavior.

### Move the live root

The live governance root moves from `aios/` to `ips-microkernel/`. There is no
compatibility directory, duplicate live route, or redirect tree at the former
path.

Current entrypoints, links, tests, and enforcement use
`ips-microkernel/`. Active machine-readable markers use the `ips-role` and
`ips-rule` namespaces. The six roles accepted by ADR-0012 remain:

- `router`
- `selector`
- `procedure`
- `reference`
- `knowledge`
- `exception`

### Keep the startup kernel thin

`GIT_AGENTS.md` and `ips-microkernel/work-router.md` remain the minimal startup
and dispatch layer. Procedures are invoked as bounded services. References
supply foundational contracts on demand. Knowledge stays dormant until a
selector observes a matching signal. Exceptions remain outside normal routes
and activate only when their qualification is proved.

`scripts/check_docs.py` continues to inspect role declarations, canonical rule
ownership, exact topology, dependencies, reachability, and retired-path
restoration under the new namespace.

### Separate human explanation from runtime context

`ips-microkernel/README.md` is human-only. It carries one dedicated
human-context marker and no runtime role or rule marker.

The repository root README may link to that page as a secondary human
navigation path. `GIT_AGENTS.md`, `AI_GUIDANCE.md`, runtime nodes, design
indexes, ADRs, delivery specifications, and other repository documents may not
link to it. The README is absent from the runtime governance graph and is not
loaded during normal iPS Microkernel execution.

The documentation checker rejects a runtime marker on the human-only README,
its inclusion in the routed surface, or an inbound link from any source other
than the repository root README.

### Preserve accepted history

ADR-0012 remains immutable historical evidence of the AIOS decision and the
transition from `docs/`. Its status changes to superseded, but its accepted
prose and filename are not rewritten.

Earlier accepted ADRs may also retain historical names and paths. Historical
evidence is not a compatibility route. The legacy `aios/` root and active
`aios-role` or `aios-rule` markers are rejected outside that immutable prose.

## Consequences

### Positive

- The architecture name now identifies intentional progressive disclosure as
  its central mechanism.
- The product identity and governance architecture remain separately legible.
- The origin story is discoverable by humans without consuming normal agent
  context.
- The thin kernel, external services, dormant knowledge, and qualified
  exceptions have one coherent explanatory model.
- Active filesystem, marker, test, and checker terminology agree.
- Automated checks prevent both legacy-route restoration and accidental
  routing of the human-only narrative.

### Costs

- The migration touches active links, tests, checker inventories, and current
  guidance even though product runtime behavior is unchanged.
- Contributors must preserve the exact `iPS Microkernel` styling and distinguish
  human navigation from runtime routing.
- Historical ADRs intentionally retain AIOS terminology, so searches require
  distinguishing historical evidence from active governance.

## Rejected alternatives

- Keep AIOS and explain the new metaphor without renaming the architecture.
- Rename only the display name while retaining the live `aios/` path and
  markers.
- Preserve `aios/` as a compatibility directory or duplicate live route.
- Put the complete origin story in the product-first repository README.
- Route the architecture README from the work router and pay its context cost
  during normal execution.
- Treat the explanatory README as another runtime role.

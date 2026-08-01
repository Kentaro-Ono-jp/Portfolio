# ADR-0020: Authorize an owner-controlled focus scratchpad

- Status: Accepted
- Date: 2026-08-01
- Deciders: ReactorFront
- Related: ADR-0008, ADR-0014, ADR-0019, Issue #65, tracking Issue #27

## Context

A focused Issue can require the implementation agent to retain exact local
state while temporarily loading another routed body of guidance. Typical
examples include publication Gate A, selected CI Playbook leaves, Stage B, and
correction or reconciliation routes. Reconstructing the implementation state
after that context switch can cost more active context than a small local
checkpoint.

Tracked handoff documents are the wrong mechanism. They become repository
surface, invite lifecycle and cleanup requirements, and risk being mistaken
for accepted evidence or authority. A mandatory checkpoint mechanism is also
counterproductive: deciding when and how to write it would itself consume
attention even when reconstruction is cheap.

The repository owner is willing to accept responsibility for an unrestricted
local workspace and its eventual cleanup. The implementation agent therefore
needs permission, not a prescribed memory system.

## Decision

Create `.noel-focus/` as an owner-controlled, Git-ignored local workspace. The
implementation agent has full discretion over everything beneath that
directory, including whether to use it and whether to create, read, update,
execute, reorganize, retain, or delete files and directories.

The delegation has no required trigger, layout, template, naming scheme, size,
retention period, cleanup, reporting, reconciliation, or use/non-use record.
Focus completion does not require the agent to inspect or remove old material.
The repository owner accepts responsibility for contents, storage, retention,
and eventual cleanup.

The work router exposes only a thin optional link. The detailed reference is
read only after the implementation agent decides to use the scratchpad. No
tracked template, bootstrap file, or executable is provided.

Scratchpad contents are local working material. Their existence does not make
them repository evidence, authority, accepted design, delivery state, proof,
or a source of truth. Effects outside `.noel-focus/` continue through the
ordinary actor-authority and delivery lifecycle.

## Consequences

### Positive

- The implementation agent can externalize a small checkpoint when that is
  cheaper than reconstructing current state.
- Routine work loads only a thin router link and pays no scratchpad protocol
  cost.
- The agent may retain richer notes or helper scripts when useful without
  expanding the tracked repository surface.
- Focus completion creates no agent cleanup burden.

### Costs

- Local scratch data may accumulate until the repository owner removes it.
- Scratch content is not independently reviewed or synchronized across
  workspaces.
- The agent must distinguish local working material from repository-backed
  authority and evidence when returning to the normal lifecycle.

## Rejected alternatives

### Require a checkpoint at named lifecycle transitions

Rejected because the useful trigger depends on active-context cost, which the
implementation agent is best placed to judge at runtime.

### Prescribe folders, templates, size limits, or retention rules

Rejected because each prescription adds attention and I/O overhead to a
workspace whose purpose is to reduce that overhead.

### Require focus-end cleanup or reconciliation

Rejected because the owner accepts responsibility for storage, retention, and
eventual cleanup; assigning that work to the implementation agent would add a
new completion obligation without improving candidate proof.

### Track a bootstrap file or canonical memo

Rejected because tracked scratch artifacts could be mistaken for durable
handoff state and would enlarge review and evidence surfaces.

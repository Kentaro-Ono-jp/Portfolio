# ADR-0015: Keep the human origin narrative unlinked

- Status: Accepted
- Date: 2026-07-28
- Deciders: ReactorFront
- Amends: ADR-0013 human-only narrative topology
- Related: ADR-0014, Issue #46, PR #45 review

## Context

ADR-0013 named the iPS Microkernel and separated its human explanation from
the runtime governance graph. It also selected a README filename, a repository
root navigation entry, and a filename-specific inbound-link checker.

The repository later selected a quieter topology. The human origin narrative
is not advertised through repository navigation. A person encounters it only
by browsing the iPS Microkernel directory or noticing the file directly.

The accepted ADR-0013 text remains immutable historical evidence, but its
human-navigation and checker decisions no longer describe the selected
topology.

## Decision

### Keep the narrative outside repository navigation

The human origin narrative has no repository navigation entry and is not a
README.

Its location is not registered in runtime routers, design indexes, repository
structure summaries, or filename-specific checker inventories. The document's
human-only context marker, rather than its filename, distinguishes it from
runtime nodes.

### Do not create a link-prohibition guard

The absence of inbound navigation is the current repository state, not a
permanent prohibition.

This decision does not establish a filename-specific inbound-link checker or a
mandatory recurrence-prevention test. A future focused decision may select a
different topology without violating this record.

### Keep the narrative self-description current

The English and Japanese descriptions must state the selected topology without
claiming retired root-README discovery, README identity, or an inbound-link
checker.

Japanese prose uses structural Markdown line breaks only. Ordinary paragraphs
remain on one physical line so rendered soft breaks do not introduce visible
spaces into Japanese sentences.

### Leave public-safety scanning undecided

This ADR does not change or settle whether a human-only narrative participates
in the public-safety scan. That boundary requires a separately selected
outcome.

## Consequences

### Positive

- The narrative can be discovered only through deliberate repository browsing.
- Runtime agents do not load the narrative during normal routing.
- Current prose no longer describes retired navigation or checker behavior.
- Japanese rendering does not inherit English-style soft-break spaces.
- ADR-0013 remains intact while the later topology decision is explicit.

### Costs

- The narrative has no convenient repository navigation path.
- Linklessness is not protected by a filename-specific regression guard.
- Long Japanese source lines are intentional.

## Rejected alternatives

### Rewrite ADR-0013

Rejected because accepted ADR prose is immutable historical evidence.

### Restore root-README navigation

Rejected because the selected topology intentionally leaves the narrative
unadvertised.

### Add a permanent inbound-link prohibition

Rejected because recurrence prevention is not selected and repository states
remain revisitable.

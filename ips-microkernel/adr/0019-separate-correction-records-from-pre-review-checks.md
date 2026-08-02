# ADR-0019: Separate correction records, Stage B checks, and the pre-push CI Playbook

- Status: Accepted
- Date: 2026-08-01
- Deciders: ReactorFront
- Supersedes: ADR-0018
- Amends: ADR-0017 direct-implementer promotion boundary
- Related: ADR-0014, ADR-0016, Issue #63

## Context

ADR-0018 coupled correction recording, prevention, reusable-knowledge
admission, and proof. An implementation actor inspected admitted past mistakes
in publication Gate A, classified a correction lesson, changed repository
knowledge, restarted Gate A when `HEAD` moved, and then used candidate proof as
if it also certified the recorded lesson.

That route retained avoidable active context and encouraged three incorrect
assumptions:

- that a correction occurrence must be deduplicated into a permanent rule;
- that a Stage B check or CI correction note must be proved before it can be
  written; and
- that the CI Playbook could be read after remote push during the short period
  before GitHub Actions starts.

Remote push is the submission boundary. Test and proof scripts must already be
hardened when `git push` publishes the candidate. A point-in-time successful
run proves that repository candidate, not the timeless correctness of every
operational note used to prepare it.

Repeated implementation and CI corrections are useful occurrence data. Their
write path must not load historical records merely to deduplicate them. Stage
B has a different purpose: it stays a small deduplicated set of mechanically
decidable checks executed after successful exact-head CI or the complete
machine-qualified no-run exception and immediately before review. An absent
workflow under that exception is a limitation, never passing evidence.

## Decision

### Keep the names distinct

Implementation Prune Stage A and Stage B are not publication Gate A and Gate
B, and neither is a CI Playbook phase.

- **Implementation Prune Stage A** records implementation-correction
  occurrences.
- **Implementation Prune Stage B** executes post-proof-or-qualified-limitation
  pre-review machine checks.
- **Publication Gate A** hardens a complete candidate before remote push and
  reads selected CI Playbook leaves.
- **Publication Gate B** prepares independent-review dispatch after successful
  exact-head CI or the complete machine-qualified no-run exception and executes
  Stage B.
- **CI Playbook** has no Stage A/B or proved/unproved classification.

### Make Implementation Prune Stage A an occurrence ledger

After a concrete implementation correction exists, append one occurrence to
the current PR record. Each occurrence contains exactly:

- the PR number;
- the observed implementation mistake; and
- the concrete correction applied.

The actor reads only the ledger contract and current PR record. First-pass
implementation, pre-push hardening, CI Playbook selection, and publication
Gate A never enumerate or read prior Stage A occurrence files.

Duplicate Mistake and Correction text is deliberate. Do not search, merge,
deduplicate, rewrite, or delete prior occurrences merely because a mistake
recurs. An occurrence records what was changed; it has no Evidence, Proof,
Status, permanence, or reusable-rule claim.

Write the occurrence immediately after the correction. Do not wait for CI,
review, merge, or a proof push. It travels with the next ordinary candidate
push. Never create a push or CI run solely to certify a Stage A occurrence.

### Keep Implementation Prune Stage B as a post-CI pre-review check

Stage B runs only after successful exact-head GitHub Actions or after the exact
head fully satisfies the governed machine-qualified no-run exception, and
immediately before initial review or re-review dispatch. Normal Actions proof
remains the default. A missing workflow under the exception is a qualified
limitation, never passing evidence. Stage B is not a correction ledger and is
never used for CI-failure recording.

Every Stage B rule supplies:

- the condition that triggers the rule;
- whether the detected problem's repair is `neutral` or `moving` for Git
  `HEAD`;
- the problem;
- a mechanically decidable detection method;
- the pass condition;
- a concrete repair procedure; and
- origin PR references, which are provenance rather than proof.

Rule titles are unique. Repeated signals strengthen one canonical rule rather
than create duplicates. Stage B has no proved/unproved state and no `none`
record.

After an adjudicated review finding is concretely corrected, add or strengthen
a Stage B rule only when the finding can become a cheap, unambiguous,
machine-decidable pre-review check. Record it after correction, without waiting
for proof or merge. If no rule qualifies, write nothing.

#### Stage B problem whose repair moves HEAD

Correct the repository file, append Stage A when the correction is an
implementation correction, then return through pre-push CI Playbook hardening,
one ordinary push, new exact-head Actions proof or the complete
machine-qualified no-run exception, and Stage B. If the existing Stage B rule
detected the problem, do not duplicate it. Improve that rule only when its
detection, pass condition, or repair procedure was incomplete.

#### Stage B problem whose repair is HEAD-neutral

A problem corrected through PR title/body, endpoint metadata, base/head SHA
publication, or another HEAD-neutral surface automatically meets the Stage B
recording requirement. Correct the live surface first and read it back. Then
add or strengthen one deduplicated `neutral` rule whose detection and repair
text are optimized for mechanical execution.

The new or strengthened rule need not be proved. Do not require an additional
push or CI run solely to certify it. If persisting the rule in the repository
later moves PR `HEAD`, ordinary candidate proof through exact-head Actions or
the complete machine-qualified exception applies because the repository
candidate changed, not because Stage B admission requires certification.

### Make the CI Playbook a pre-push correction notebook

The CI Playbook is read before remote push, never after push while waiting for
GitHub Actions. Publication Gate A selects only leaves triggered by the
complete current Proof delta. The actor applies relevant records to the
current candidate and repairs test or proof scripts before push.

CI Playbook entries are fallible operational correction notes, not admitted
reusable knowledge or permanent truth. They have no Evidence requirement and
no proved/unproved or promotion state.

After correcting the root cause of an exact-head CI failure, immediately
append the observed CI mistake or failure and the concrete correction to the
matching leaf. Do not write an unresolved symptom or pre-correction guess. Do
not scan existing entries for reuse or deduplication; duplicate entries are
allowed. Do not wait for successful CI, review, merge, or a dedicated proof
push.

The next ordinary candidate cycle selects the relevant leaf before remote
push. It may contain duplicate, outdated, or unproved notes. The actor compares
them with accepted design and the current candidate and repairs applicable
test/proof scripts in place. If later CI disproves a correction, correct again
and append another note rather than assigning a proof status.

Selector-based leaf loading remains mandatory so unrelated Playbook history
does not enter active context.

### Separate operational recording from candidate proof

Recording never proves a Stage A occurrence, Stage B rule, or CI Playbook
entry. Conversely, removing their proof prerequisite does not weaken the
candidate lifecycle.

Every repository candidate still requires a pushed exact head, exact-head
GitHub Actions or its machine-qualified exception, independent review of that
same head, a merge pinned to the reviewed head, and merged-main
reconciliation. A repository change made only to persist an operational rule
still receives ordinary candidate proof when it moves `HEAD`; that proof does
not convert the rule into certified permanent truth.

Material governance continues through a focused Issue and ADR. Operational
records do not automatically enter the evidence-bound Knowledge Curator or
become permanent governance decisions.

## Consequences

### Positive

- Correction detail leaves active context immediately after the correction.
- Stage A and CI Playbook writers do not load history to deduplicate it.
- CI Playbook use occurs at the actual pre-push hardening boundary.
- Stage B remains bounded, mechanical, deduplicated, and directly repairable.
- HEAD-neutral publication mistakes become explicit reusable Stage B checks.
- Candidate proof and operational-record truth are no longer conflated.

### Costs

- Stage A and CI Playbook data grow with duplicate occurrences by design.
- CI Playbook readers must tolerate duplicate, outdated, and unproved notes.
- Stage B may contain unproved rules and must provide mechanical detection and
  repair text instead of relying on authority labels.
- Persisting a repository-backed Stage B rule may move `HEAD` and therefore
  require ordinary candidate proof even though rule admission itself requires
  no proof.

## Rejected alternatives

### Read Stage A history before implementation or push

Rejected because Stage A is occurrence data, and loading it recreates the
active-context cost this decision removes.

### Deduplicate Stage A or CI Playbook records

Rejected because write-time comparison expands context and repeated
occurrences are intentionally preserved.

### Split CI Playbook entries into proved and unproved stores

Rejected because every entry is an operational correction note. Current
candidate judgment and CI handle present applicability; a status split does
not make the note timeless.

### Read the CI Playbook after push but before CI starts

Rejected because remote push already submitted the candidate. Any repository
repair after push creates a new head and requires a new candidate cycle.

### Add Stage B rules before correction

Rejected because unresolved assertions and symptoms do not describe a
concrete detection and repair path.

### Require proof before operational recording

Rejected because proof belongs to the repository candidate. Operational
recording describes a completed correction or an executable check and has no
proved/unproved state.

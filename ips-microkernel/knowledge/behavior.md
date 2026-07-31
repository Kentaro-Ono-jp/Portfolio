# Behavior implementation careless-mistake guide

<!-- ips-role: knowledge -->
<!-- ips-rule: behavior-careless-mistake-guide -->

## Read when

Do not read this guide before the first complete Behavior implementation. Read
only the applicable phase: `pre-CI` in Gate A after the complete local behavior
delta is committed, or `pre-review` in Gate B after exact-head CI succeeds.

## Entry contract

Add a reusable entry only when stable real review or CI evidence exists,
recurrence is plausible, the check has a clear actionable answer, the check is
cheap compared with another dispatch cycle, and the lesson changes future
Behavior implementation. Each entry contains exactly Phase, Trigger, Mistake,
Check, Guard, and Evidence. Do not store material design decisions, one-off
product bugs, speculation, secrets, private payloads, or an incident ledger.

## Entries

### Authenticate before request validation

- **Phase:** `pre-CI`
- **Trigger:** A protected request boundary adds or changes path, header, body,
  or multipart validation.
- **Mistake:** Anonymous malformed input reaches validation before the
  capability-specific authentication boundary.
- **Check:** Does authentication fail closed before every affected validation
  path, including malformed unauthenticated input?
- **Guard:** Exercise anonymous and authenticated malformed requests; require
  canonical authentication failure before validation and zero protected service
  calls for the anonymous cases.
- **Evidence:** PR #57
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5142938286).

### Publish exact review endpoints

- **Phase:** `pre-review`
- **Trigger:** Initial review or re-review is ready to dispatch.
- **Mistake:** The PR description names a branch or head but omits the exact
  full live base and head SHAs.
- **Check:** Do the current-review base and head in the live PR description
  equal the live PR endpoints exactly?
- **Guard:** Read live base/head, update both full SHAs in the PR body and review
  prompt, then read the body back before dispatch.
- **Evidence:** PR #57
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5143276537).

### Invalidate head-bound review evidence

- **Phase:** `pre-review`
- **Trigger:** A correction push moved the PR head before re-review.
- **Mistake:** The PR description or prompt presents old endpoints, CI, or a
  previous verdict as current-head evidence.
- **Check:** Are current and preceding evidence classified against the live
  head, with every correction and lifecycle link present?
- **Guard:** Require live pushed-head equality, exact-head successful CI, and a
  metadata read-back before reviewer dispatch.
- **Evidence:** PR #57
  [approved correction](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5143423042).

## Phase boundary

A failed `pre-CI` entry blocks push. A failed `pre-review` entry blocks reviewer
dispatch. Editing only the PR title or body does not change the Git commit,
branch ref, tree, or PR head SHA, so successful exact-head CI remains valid.
Any repository-file correction, including this guide, moves HEAD after commit
and returns through Gate A, push read-back, and new exact-head CI.

## Direct write-back

After a review or CI correction, classify every reusable careless-mistake
lesson before the next push. Strengthen an existing atomic entry when it owns
the lesson; otherwise add one entry in the correct phase. Split compound
Behavior and Proof lessons and write the Proof part through the CI knowledge
selector. If no lesson meets the entry contract, publish `Knowledge
write-back: none` with a concrete rationale in the PR correction evidence.
There is no pending intake queue.

## Return

Return to the calling Gate A or Gate B workflow after checking only the current
phase and triggered entries.

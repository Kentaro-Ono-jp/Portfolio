# Independent PR review router

<!-- docforai-role: router -->
<!-- docforai-rule: review-permission-boundary -->

Use this router only in a separate initial-review or re-review task. Earlier
chat and implementation-agent memory are not inputs. Do not preload all review
states.

## Required inputs

- Repository URL
- Pull request URL
- Governing tracking Issue URL
- Focused Issue URL
- Expected full base SHA
- Expected full head SHA
- Review cycle: `initial` or `re-review`
- Previous verdict URL for re-review, otherwise `none`

Missing or contradictory input is a limitation, not permission to infer
current state.

## Permission boundary

The reviewer leaves the canonical workspace untouched, works in one isolated
shallow clone, uses non-Docker static verification, and makes exactly one
GitHub write: a top-level verdict comment for this review cycle.

The only permitted GitHub write is that verdict comment. Do not push, create
or delete branches, edit or close an Issue or PR, resolve threads, change
Draft or Ready state, merge, rerun or cancel workflows, change settings, or
make any other GitHub mutation. Do not modify implementation to fix a finding.

## State sequence

1. Start with [review setup](review/setup.md).
2. Setup routes to inspection only after the exact head and isolated clone are
   proved.
3. Inspection routes to verdict only after the full diff and applicable
   evidence are judged.
4. Verdict routes to cleanup only after the single GitHub comment is
   published.
5. Cleanup ends the review task and reports its result without a second GitHub
   write.

At each transition open only the named next state. If a guard prevents the
transition, publish only the permitted limitation or verdict and do not skip
ahead.

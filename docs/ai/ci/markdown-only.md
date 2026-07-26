# Machine-qualified Markdown-only CI exception

<!-- docforai-role: procedure -->
<!-- docforai-rule: ci-markdown-only-exception -->

## Read when

Read this file only when the complete candidate may qualify for an Actions skip
for its exact Markdown-only PR head and merge. Every supported skip form is
prohibited outside this machine-qualified exception.

GitHub-supported forms are `[skip ci]`, `[ci skip]`, `[no ci]`,
`[skip actions]`, `[actions skip]`, and the `skip-checks` trailer described by
the official
[skip instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).

## Required conditions

1. Require the exact PR base to be the then-current `main` baseline. Record its
   SHA and latest applicable successful runtime proof. Intervening qualified
   Markdown-only merges need no new runtime proof.
2. Require every path in the complete base-to-head diff to end in `.md`.
   Changes must be non-executable wording, evidence, links, or review cleanup;
   no workflow, script, test, configuration, dependency, or application
   behavior may change.
3. Require `python scripts/check_docs.py` and `git diff --check` to pass on the
   review head.
4. Require the review-head commit to carry a GitHub-supported skip instruction
   and receive independent exact-head review.
5. If any condition is uncertain or false, use normal exact-head Actions proof
   without pausing for a policy decision.

## PR description

Record:

- current review head
- automatic qualification result
- exact base `main` SHA, workflow event, and successful run link
- exact Markdown file count and path list in the complete PR diff
- review-head local documentation results
- explicit confirmation that no exact-head Actions run exists or is claimed

Any failed condition restores normal exact-head Actions proof.
An absent run is never passing evidence.

## Independent review

The reviewer independently verifies the exact base, full Markdown-only file
boundary, local documentation proof, intended skip instruction, and absent
run. The missing exact-head run is a qualified limitation, never passing
evidence.

## Squash merge boundary

When the established merge method is squash:

1. Pin merge to the independently reviewed PR head.
2. Supply an explicit squash subject and body that summarize the reviewed PR
   without copying component commit subjects.
3. Put one supported skip instruction in that explicit message so the
   Markdown-only `main` commit also skips Actions.
4. Do not accept the hosting service's generated default squash body.
5. After merge, read the exact merge message, require the intended instruction,
   and confirm no run exists for the merge SHA.
6. Do not dispatch a workflow, rerun one, or create a trigger commit.

The PR-head and default-branch skips are one exception. Neither absent run is
runtime passing evidence.

## Return

Return to the calling preflight, publication, review, merge, or reconciliation
state with the exact exception evidence. Do not open unrelated CI knowledge.

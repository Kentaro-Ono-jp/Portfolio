# Independent PR review and re-review

Use this file in a separate review task. It is the complete review contract;
earlier chat and implementation-agent memory are not inputs.

## Required inputs

- Repository URL
- Pull request URL
- Focused Issue URL
- Expected full head SHA
- Review cycle: `initial` or `re-review`
- Previous verdict URL for re-review, otherwise `none`

Missing or contradictory input is a limitation, not permission to infer
current state.

## Permission boundary

The review agent must:

- leave the canonical local workspace untouched
- use a unique isolated temporary directory
- shallow-clone only the exact PR head with `--depth 1` and `--no-tags`
- use GitHub reads and non-Docker static verification as needed
- make exactly one top-level verdict comment for this review cycle
- after that comment, remove the clone and every generated temporary file,
  verify the temporary path no longer exists, and report the result in the
  review task's final response

The only permitted GitHub write is that verdict comment. Do not push, create
or delete branches, edit or close an Issue or PR, resolve threads, change Draft
or Ready state, merge, rerun or cancel workflows, change settings, or perform
any other GitHub mutation.

Do not modify implementation to fix a finding.

## Procedure

1. Read [GIT_AGENTS.md](../../GIT_AGENTS.md),
   [the AI contract](README.md), accepted ADRs in numeric order, Delivery
   Specification 0001, the focused Issue, and the complete PR description.
2. For re-review, read the previous verdict and the implementation response.
   Verify each prior finding against the new code; do not limit review to those
   findings.
3. Resolve the live PR head and require it to equal the expected full SHA.
   Require the PR description's current-review head to equal the same SHA and
   its workflow evidence to distinguish exact-head, preceding, superseded, and
   intentionally absent results accurately.
4. Create the isolated shallow clone. Require `git rev-parse HEAD` to equal the
   expected SHA.
5. Inspect the complete pull request diff against its stated base. Judge
   behavior against scope, non-targets, failure model, acceptance criteria,
   accepted design, tests, and public safety.
6. Run the smallest relevant non-Docker static verification. Do not start or
   mutate Docker Desktop. Read the exact-head Actions result and limitations.
   When the owner approved the
   [CI playbook's Markdown-only skip](../../.github/workflows/CI_PLAYBOOK.md),
   verify the exact base `main` SHA and its successful default-branch run,
   require every path in the complete base-to-expected-head PR diff to be
   Markdown-only, run the review-head documentation checks, and report the
   absent exact-head run as a limitation rather than passing evidence. This
   narrow exception applies to initial review and re-review and does not itself
   prevent approval.
7. Classify actionable findings by severity and cite exact file/line or
   behavioral evidence. Do not request speculative scope expansion.
8. Publish one verdict comment using the format below. Record temporary-data
   cleanup as `scheduled immediately after this comment`; do not claim it is
   already complete.
9. Delete the shallow clone and generated data after the GitHub write:
   - first require the deletion target to be the already verified, uniquely
     named child created for this review under the platform temporary root
   - use the environment's ordinary scoped deletion mechanism first
   - if shell or execution policy rejects that mechanism, use a standard
     library directory API in the same process against that exact validated
     path only; do not broaden the target or run global cleanup
   - if that exact deletion fails only on read-only descendants, revalidate
     that every residual entry remains under the same target, do not traverse
     reparse-point targets, clear only the `ReadOnly` attribute with the same
     process's standard library, and retry deletion of the same fixed root
   - do not change access-control lists, take ownership, terminate processes,
     or expand the deletion target to force cleanup
   - verify the temporary path no longer exists
10. In the review task's final response, report the verdict URL and actual
    cleanup result. If cleanup fails, report the exact limitation and remaining
    path to the owner; do not make a second GitHub write.

If the head moved, the PR description is stale or mislabels older evidence as
exact-head proof, required review evidence is unavailable outside the explicit
docs-only exception, or a prohibited mutation occurred before the verdict, do
not approve. Report the exact limitation in the single verdict comment. Cleanup
occurs after the verdict and therefore cannot change that comment; any cleanup
failure is a task-level limitation that must be reported to the owner without
another GitHub mutation.

## Verdict format

```markdown
## Changes requested | Approved

Reviewed head: `<full SHA>`
Review cycle: `<initial | re-review>`
Previous verdict: `<URL | none>`

### Findings or approval basis

<severity, exact evidence, and impact; for re-review include prior-finding status>

### Verification

- shallow-clone static checks: `<result>`
- exact-head GitHub Actions: `<result>`
- canonical workspace: untouched
- GitHub mutations: verdict comment only
- temporary clone and generated data: cleanup scheduled immediately after this comment
- limitations: `<result | none>`
```

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
- remove the clone and every generated temporary file, then verify the
  temporary path no longer exists

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
4. Create the isolated shallow clone. Require `git rev-parse HEAD` to equal the
   expected SHA.
5. Inspect the complete pull request diff against its stated base. Judge
   behavior against scope, non-targets, failure model, acceptance criteria,
   accepted design, tests, and public safety.
6. Run the smallest relevant non-Docker static verification. Do not start or
   mutate Docker Desktop. Read the exact-head Actions result and limitations.
7. Classify actionable findings by severity and cite exact file/line or
   behavioral evidence. Do not request speculative scope expansion.
8. Delete the shallow clone and generated data. Verify cleanup before the
   GitHub write.
9. Publish one verdict comment using the format below.

If the head moved, required evidence is unavailable, cleanup cannot be proved,
or a prohibited mutation occurred, do not approve. Report the exact limitation
in the single verdict comment.

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
- temporary clone and generated data: removed
- limitations: `<result | none>`
```

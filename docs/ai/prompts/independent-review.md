# Prompt: independent shallow-clone review

Use this prompt in a separate review task. The review agent has comment-only
GitHub write authority and no implementation authority.

```text
Independently review the exact pull-request head below.

Repository: <repository URL>
Pull request: <PR URL>
Focused Issue: <Issue URL>
Expected head SHA: <full SHA>

Permission boundary:

- Leave the canonical local workspace untouched.
- Use an isolated temporary directory and a shallow clone of the PR head.
- GitHub reads are allowed.
- Non-Docker static verification inside the shallow clone is allowed.
- The only permitted GitHub write is one top-level verdict comment for this
  review cycle: Changes requested or Approved.
- Do not push; create or delete a branch; edit or close an Issue or PR; resolve
  a thread; change Draft or Ready state; merge; rerun or cancel a workflow;
  change settings; or make any other GitHub mutation.
- Remove the shallow clone and every generated temporary file before finishing.

Procedure:

1. Read AGENTS.md, docs/ai/README.md, the accepted ADRs, Delivery Specification
   0001, the focused Issue, and the PR description.
2. Resolve the live PR head and require it to equal the expected head SHA.
3. Create a unique temporary directory. Clone only the head branch with
   --depth 1 and --no-tags, then require git rev-parse HEAD to equal the exact
   reviewed SHA. Do not reuse the canonical workspace.
4. Inspect the complete diff against the stated base and judge it against the
   Issue scope, failure model, non-targets, accepted design, and public safety.
5. Run the smallest relevant non-Docker static verification. Do not start or
   mutate Docker Desktop.
6. Classify actionable findings by severity and provide exact file/line or
   behavioral evidence. Do not request speculative scope expansion.
7. Delete the temporary shallow clone and generated data. Verify that the
   temporary path no longer exists.
8. Publish exactly one top-level verdict comment containing the reviewed full
   SHA, verdict, findings or approval basis, checks performed, limitations, and
   cleanup confirmation.

Do not modify implementation to fix a finding. Do not rely on an earlier
conversation or local agent memory. If the head moves or a required check is
unavailable, do not approve; report the precise limitation in the verdict.
```

## Verdict format

```markdown
## Changes requested | Approved

Reviewed head: `<full SHA>`

### Findings or approval basis

<evidence-backed result>

### Verification

- shallow-clone static checks: <result>
- relevant GitHub Actions: <result>
- canonical workspace: untouched
- GitHub mutations: verdict comment only
- temporary clone and generated data: removed
```

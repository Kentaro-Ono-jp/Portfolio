# AI-assisted task lifecycle

This lifecycle keeps normal orientation narrow while preserving exact checks
where a mutation can affect durable state.

## 1. Cold task bootstrap

1. Read [`docs/ai/README.md`](README.md) and its required sources.
2. Run `git status --short --branch` in the canonical workspace.
3. Read Issue #1 and only the active focused Issue, PR, and workflow run needed
   for the requested task.
4. Compare the relevant local and remote heads when the task will branch,
   push, merge, or reconcile evidence.
5. Broaden the audit only if the state is missing, stale, dirty,
   contradictory, or outside the declared actor model.

Always verify the exact target before a durable mutation.

Do not list all Issues, branches, comments, workflow history, or repository
content solely to prove that an unknown writer did not act when the trusted
baseline is consistent.

## 2. Focused planning

- Create or update one focused Issue with the outcome, scope, non-targets,
  failure model, acceptance criteria, and canonical proof.
- Start the branch from an exact, fetched `origin/main` only after a clean
  status check.
- Keep material architecture changes aligned with an ADR or delivery
  specification in the same change.
- Do not expand into adjacent application boundaries without owner approval.

## 3. Implementation and publication

- Change only files within the approved scope and preserve unrelated work.
- Use `python scripts/verify.py`; do not create a competing root verifier.
- Prefer local static verification when Docker runtime is not explicitly
  authorized. GitHub Actions is the authoritative runtime proof.
- Inspect the intended diff before explicitly staging files.
- Commit tersely, push the focused branch, and open a Draft PR linked to the
  focused Issue and Issue #1.
- Recheck the exact branch head and PR check before relying on a workflow
  result.

## 4. Independent review

Use the [independent review prompt](prompts/independent-review.md). The review
agent works only in an isolated temporary shallow clone, runs non-Docker static
verification, publishes one top-level verdict comment, and removes its clone.

When a verdict returns, the implementation agent checks:

- the SHA named by the verdict
- the current PR head
- the relevant check conclusion
- the evidence for each actionable finding

It does not audit every remote and local object merely because the review agent
ran. A mismatched SHA or prohibited mutation is a discrepancy and triggers a
targeted investigation.

## 5. Correction, Ready, and merge

- Judge every requested change against accepted design and concrete code.
- Obtain owner approval before implementing a material correction strategy.
- Push corrections, require the exact-head workflow to pass, and request a new
  independent verdict.
- Mark Ready and merge only with explicit owner direction.
- Pin the merge to the reviewed PR head and use the repository's established
  merge method.

## 6. Post-merge reconciliation

1. Fast-forward local `main` to the exact merge commit.
2. Require the default-branch workflow on that commit to pass.
3. Apply the [evidence policy](evidence-policy.md) to the focused Issue and
   Issue #1.
4. Remove only identified, authorized temporary data and the merged local
   feature branch.
5. Keep remote-branch deletion explicit; do not infer it from unrelated
   cleanup authority.
6. Update repository-owned governance when the process changed.

Use the [post-merge prompt](prompts/post-merge-reconciliation.md) for a cold
reconciliation task.

## 7. Offline and discrepancy behavior

When GitHub is unavailable, read tracked sources and perform safe offline work
only. Do not infer current PR, Issue, check, or merge state from local memory.

When observed state conflicts with this lifecycle, stop the pending mutation,
capture the narrow evidence, and ask the owner before widening scope or
repairing durable state.

# Prompt: post-merge reconciliation

Use this prompt only after the owner has authorized merge or asks to reconcile
an already merged focused increment.

```text
Reconcile the completed focused increment using repository-owned guidance and
live GitHub evidence.

Repository: <repository URL>
Focused Issue: <Issue URL>
Merged pull request: <PR URL>
Approved reviewed head: <full SHA>

Follow docs/ai/evidence-policy.md.

1. Verify the PR is merged from the approved head and record the exact merge
   commit. Do not infer either SHA from local memory.
2. Fast-forward the clean local main branch to origin/main without reset or
   discarding changes.
3. Require the default-branch GitHub Actions run for that exact merge commit to
   complete successfully. Inspect the relevant proof and teardown evidence.
4. Map every focused-Issue acceptance criterion to concrete implementation,
   review, PR-run, main-run, failure-path, scope, and cleanup evidence.
5. Check only criteria that are fully proved. Add a Completion evidence section
   with stable links and exact SHAs; preserve unproved boxes and state what is
   missing.
6. Update Issue #1 with the completed focused increment and accumulated
   evidence. Check an umbrella gate only if every criterion for the complete
   Delivery Specification step is proved.
7. Remove only identified, owner-authorized temporary data and a fully merged
   local feature branch. Keep remote-branch deletion explicit.
8. Report the final Issue counts, exact main SHA and run, local status, cleanup,
   and any remaining work.

Do not perform a broad audit solely to detect an unknown writer while the actor
model remains consistent. Stop and report any dirty workspace, moved head,
failed main run, prohibited review mutation, or contradictory evidence before
updating checklists.
```

## Expected result

The focused Issue becomes an evidence-backed delivery record, Issue #1 gains
only justified accumulated proof, and cleanup remains exact and recoverable.

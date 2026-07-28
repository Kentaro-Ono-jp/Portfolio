# Post-merge CI knowledge reconciliation

<!-- ips-role: procedure -->
<!-- ips-rule: ci-post-merge -->

## Read when

Read this file after every feature PR merge and before the next feature
increment, once the exact merge commit's automatic `push` workflow completes.

## Procedure

1. Require the exact merge SHA and completed default-branch workflow.
2. Audit only that PR's failed runs and corrective commits.
3. Separate reusable runner knowledge from product defects and review-only
   corrections.
4. For each reusable signal, use the
   [knowledge selector](../knowledge/selector.md), read one matching leaf, and return
   here. Prefer an executable regression guard over prose.
5. Revise or add one knowledge leaf only when the reusable decision rule is
   new.
6. Record the outcome in the merged feature's focused Issue:
   - link a focused playbook-update Issue and publish that reviewed update
     before the next feature increment when new knowledge exists
   - otherwise record `CI knowledge reconciliation: no new reusable finding`
     and do not create an empty documentation change

## Guard outcome

- A failed or missing exact-merge workflow returns to CI triage and leaves
  affected completion evidence open.
- An incomplete correction chain remains linked as an explicit evidence gap.
- Reinspect an unclassified reusable signal against one knowledge leaf at a
  time; if it is not reusable, record that outcome without a documentation
  change.
- Publish a knowledge change only through its focused Issue, exact proof, and
  independent review.

## Return

Return the reconciliation outcome to the post-merge workflow. Issue checklist
updates and delivery evidence are handled separately.

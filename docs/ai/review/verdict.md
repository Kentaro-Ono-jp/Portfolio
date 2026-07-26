# Independent review verdict

<!-- docforai-role: procedure -->
<!-- docforai-rule: review-verdict -->

## Read when

Read this file only after the complete exact-head inspection is finished.

## Procedure

Publish exactly one top-level PR comment for this review cycle:

```markdown
## Changes requested | Approved

Reviewed head: `<full SHA>`
Review cycle: `<initial | re-review>`
Previous verdict: `<URL | none>`

### Findings or approval basis

<severity, exact evidence, and impact; include prior-finding status for re-review>

### Reusable governance candidate

<exact reusable process or review signal and evidence | none>

### Verification

- shallow-clone static checks: `<result>`
- exact-head GitHub Actions: `<result>`
- canonical workspace: untouched
- GitHub mutations: verdict comment only
- temporary clone and generated data: cleanup scheduled immediately after this comment
- limitations: `<result | none>`
```

Do not claim cleanup is complete before the comment. Cleanup occurs after the
only permitted GitHub write.

The reusable-governance candidate is evidence for the implementation
lifecycle's post-merge classification. It is not permission for the reviewer
to edit guidance, implementation, an Issue, or the PR.

## Publication guard

If the comment cannot accurately state the reviewed SHA, evidence,
reusable-governance candidate, limitations, and scheduled cleanup, do not
publish a partial verdict.

## Next

Immediately after the comment, open [review cleanup](cleanup.md). No other
GitHub action is permitted.

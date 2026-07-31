# Independent review verdict

<!-- ips-role: procedure -->
<!-- ips-rule: review-verdict -->

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

<exactly one of:

`none`

or one numbered item for every atomic reusable candidate:

1. **Signal:** `<one atomic reusable process or review signal>` — **Evidence:** `<exact evidence>`
2. **Signal:** `<next atomic signal; repeat once per remaining candidate>` — **Evidence:** `<exact evidence>`
>

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

Keep exactly one candidate section. When candidates exist, use their stable
discovery order and one numbered item for every atomic reusable candidate.
`none` is permitted only when no reusable candidate was discovered; never use
it as a substitute for a second or later item.

The reusable-governance candidates are evidence for routed knowledge curation.
They are not permission for the reviewer to classify a disposition or edit
guidance, implementation, an Issue, or the PR.

## Publication guard

If the comment cannot accurately state the reviewed SHA, evidence, every
reusable-governance candidate or valid `none`, limitations, and scheduled
cleanup, do not publish a partial verdict.

## Next

Immediately after the comment, open [review cleanup](cleanup.md). No other
GitHub action is permitted.

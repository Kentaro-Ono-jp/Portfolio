# CI evidence and teardown knowledge

<!-- aios-role: knowledge -->
<!-- aios-rule: ci-knowledge-evidence -->

## Read when

Read this file when changing diagnostics, artifacts, leakage scanning, failure
ordering, or teardown.

## Durable rules

- Preserve the first causal failure even when diagnostics or cleanup also fail.
- Sanitize and upload useful evidence without credentials or private input.
- Artifact failure must not suppress unconditional teardown.
- Teardown targets only the `reactorfront-portfolio` project and owned
  ephemeral resources.
- Never run Docker prune or unscoped cleanup.
- Local execution does not inherit ephemeral-runner volume removal.

The canonical workflow and verifier must make successful and failing paths
execute scoped teardown.

## Return

Return to the calling CI procedure after failure preservation, sanitization,
and scoped ownership are proved.

# Curated AI prompts

These prompts are public engineering artifacts for repeatable portfolio work.
They define inputs, permissions, evidence, and stopping conditions without
depending on an earlier conversation or machine-local memory.

- [Cold task bootstrap](task-bootstrap.md) reconstructs the relevant state with
  bounded live checks.
- [Independent review](independent-review.md) performs an isolated,
  comment-only review of an exact PR head.
- [Post-merge reconciliation](post-merge-reconciliation.md) updates evidence
  only after the exact merge commit passes on the default branch.

Replace angle-bracket placeholders with the current public identifiers. Do not
paste credentials, personal data, private-client context, raw conversations,
hidden reasoning, or a local-memory export into a prompt or its evidence.

These templates do not grant authority. The repository owner still approves
scope expansion, material correction strategies, Ready state, merge, Issue
reconciliation, and destructive cleanup.

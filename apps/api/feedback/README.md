# Feedback-candidate export

The API-owned feedback exporter projects eligible terminal review evidence into
one canonical, sanitized document. The document is a curation input only. It is
not a dataset snapshot, training instruction, evaluation result, promotion
decision, or runtime model selector.

## Export

Run the command from the repository root with the exact reviewed corpus
inventory intended for eligibility:

```console
uv run --project apps/api python -m reactorfront_api.feedback_export_main \
  --inventory apps/ml/evaluation/corpus/v1/corpus.json \
  > feedback-candidates.json
```

The command reads PostgreSQL through the API-owned connection and writes the
complete document to standard output only after inventory validation, the
read-only query, projection, canonical serialization, and digest calculation
succeed. Stable error output contains only a failure code. The command does not
read object storage or corpus source files and cannot write a corpus, split,
snapshot, artifact, evaluation report, or promotion manifest.

The v1 schema is
[feedback-candidate-export-v1.schema.json](feedback-candidate-export-v1.schema.json).
Each candidate contains only its digest-derived identity, source digest,
machine and final classifications, review outcome, and measured model lineage.
Omissions disclose only stable aggregate reason codes and counts.

## Explicit curation

Export never admits learning data. To consider a candidate for a later dataset:

1. Verify the export schema, `exportSha256`, and `inventorySha256` against the
   exact reviewed inventory used by the command.
2. Compare only the allowlisted candidate fields with the repository-owned
   synthetic source and its accepted provenance. Do not recover or copy actor,
   document, job, timestamp, comment, filename, database, or source-content
   context from runtime state.
3. Open a new focused Issue that names the proposed source, label, family,
   license, split effect, leakage proof, dataset version, and non-targets.
4. Admit the source only through a normal repository change with independent
   review, canonical snapshot regeneration, leakage checks, evaluation proof,
   and owner-authorized merge.
5. Keep candidate training, evaluation, promotion, and runtime selection in
   their separately reviewed increments.

An unmatched digest, conflicting observation, legacy result, incomplete
lineage, or unsupported label remains ineligible. An exported approval or
correction is product evidence, not automatic consent to train.

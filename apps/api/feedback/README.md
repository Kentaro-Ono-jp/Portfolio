# Feedback-candidate export

The API-owned feedback exporter projects eligible terminal review evidence into
one canonical, sanitized document. The document is a curation input only. It is
not a dataset snapshot, training instruction, evaluation result, promotion
decision, or runtime model selector.

## Export

Run the command from the repository root with the exact reviewed feedback
source-identity inventory intended for eligibility:

```console
uv run --project apps/api python -m reactorfront_api.feedback_export_main \
  --inventory apps/api/feedback/feedback-source-inventory-v1.json \
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
The reviewed inventory binds each canonical corpus text digest to the exact
SHA-256 of the deterministic, uploadable PDF fixture produced by
`scripts/pdf_fixture.py`; it also pins the corpus inventory and fixture-generator
digests. The candidate `sourceSha256` is that PDF digest, so it is the same
identity computed and persisted by the production upload boundary. The command
does not read the corpus text or generator at runtime; unit proof recomputes all
bindings and the real-PostgreSQL proof originates the selected row through the
production submission service.

Each candidate contains only its digest-derived identity, upload source digest,
machine and final classifications, review outcome, and measured model lineage.
Omissions disclose only stable aggregate reason codes and counts.

## Explicit curation

Export never admits learning data. To consider a candidate for a later dataset:

1. Verify the export schema, `exportSha256`, and `inventorySha256` against the
   exact reviewed inventory used by the command.
2. Resolve `sourceSha256` only through the exact reviewed binding to its
   canonical corpus digest, then compare the allowlisted candidate fields with
   that repository-owned synthetic source and its accepted provenance. Do not
   recover or copy actor,
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

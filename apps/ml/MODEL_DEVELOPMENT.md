# Governed model-development summary

This record explains the bounded model-development path implemented by the
third vertical slice. It is public engineering evidence for a repository-owned
synthetic demonstration, not a production model-quality report.

## Development boundary

Runtime review evidence cannot train or select a model by itself. The API may
export only a canonical minimal feedback candidate whose source digest already
belongs to the reviewed synthetic inventory. Export omits source bytes and
text, filenames, document and job identifiers, correlation and principal
identifiers, actor identity, tokens, timestamps, comments, and database keys. A
separate reviewed curation change is required before any matching repository-
owned source can enter a dataset snapshot.

The immutable `reactorfront-synthetic-documents-v1` snapshot contains 18
repository-authored English samples across ten source/template families. Its
fixed family-disjoint assignment is 12 train, two validation, and four held-out
test samples. Candidate fitting uses only the declared training membership;
the held-out test membership and numeric policy were accepted first in
[Issue #77](https://github.com/Kentaro-Ono-jp/Portfolio/issues/77) and
[PR #78](https://github.com/Kentaro-Ono-jp/Portfolio/pull/78).

## Reproducible identities

| Evidence | Version or SHA-256 | Repository record |
|---|---|---|
| Dataset | `reactorfront-synthetic-documents-v1` / `e82005c8ca78b7966f24e1faaf2a2b161262f1e774dc813e0c2d0743280cb046` | [`snapshot.json`](evaluation/corpus/v1/snapshot.json) |
| Split | `family-disjoint-v1` / `4a2b00a69b0ea2df152f8c80d4d61a5f0d3d55be87a18b4d29a3cda7ff18bc65` | [`split.json`](evaluation/corpus/v1/split.json) |
| Preprocessing | `nfkc-ascii-alphanumeric-bow-v1` | [`policy-v1.json`](evaluation/policy-v1.json) |
| Pipeline | `pytorch-multinomial-naive-bayes-linear-v1` | [`candidate-build-v1.json`](evaluation/candidate-build-v1.json) |
| Evaluation policy | `document-classification-evaluation-v1` / `e3431c6d4e9094b8bd88b77a4ba4abc860641d7f83eaf71a5ee71c8f46bae332` | [`policy-v1.json`](evaluation/policy-v1.json) |
| Promoted artifact | `document-type-candidate-v1` / `970723c2d4a11cce2567f931e55cc4f673dc0f359a9d0e0e8730136dc661e9ae` | [`candidate-build-v1.json`](evaluation/candidate-build-v1.json) |
| Candidate report | `4562e0cda501400a8e1988bb0463bac4b9c12537da9b985ebe31e0c897e4fa18` | [`candidate-report-v1.json`](evaluation/candidate-report-v1.json) |
| Comparison | `0a19deef4081cd4ff8ee974c9a0b584fcfb3a37d77753a3dd7fd3348c923bfca` | [`candidate-comparison-v1.json`](evaluation/candidate-comparison-v1.json) |
| Promotion manifest | `f4a4f68d93fdc04c75c4ad624a5004319a53aad41e514061a9b6675254cd308c` | [`promoted-model-v1.json`](evaluation/promoted-model-v1.json) |
| Rollback artifact | `document-type-v1` / `82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac` | [`champion-baseline-v1.json`](evaluation/champion-baseline-v1.json) |

Canonical verification reconstructs the promoted artifact from the fixed 12
training samples, evaluates it twice, requires byte-identical reports, and
recomputes every absolute and champion-relative gate. Corrupted lineage,
partial reports, leakage, non-finite metrics, ineligible candidates, and an
unreviewed newest artifact fail closed without changing the selected manifest.

## Bounded evaluation result

Both the candidate and prior champion process all four held-out synthetic
samples. The candidate report records macro F1 `1.0`, invoice/report precision,
recall, and F1 of `1.0`, mean true-label model score `0.99982216`, and no
sanitized failure. The comparison records zero regression and passes the
predeclared absolute and champion-relative gates.

Four held-out repository-authored samples cannot establish production
accuracy, calibration, fairness, privacy, robustness, generalization, or
performance under domain drift. No calibration procedure is fitted; the
displayed value is a model score, not a calibrated probability. See the
[model card](MODEL_CARD.md) for intended use and limitations.

## Promotion, runtime, and human decisions

Promotion is one reviewed repository mutation. The sole manifest selects the
exact dataset, preprocessing, pipeline, policy, report, comparison, artifact,
and `invoice`/`report` ontology. The ML image generates only that artifact;
startup and readiness independently validate the complete identity before
processing. Rollback is another reviewed manifest change selecting the exact
previously accepted `document-type-v1` lineage.

New `completed.v2` events carry the selected immutable lineage through API
persistence, review ETags, audit evidence, OpenAPI, generated Web types, and
the authenticated result. Existing results remain explicitly
`legacy-unmeasured`. Human approval or correction is stored separately and
cannot rewrite the machine result, its lineage, prior audit evidence, or the
promotion decision.

The focused implementation and authoritative proof for every boundary are
recorded in [Delivery Specification 0003](../../ips-microkernel/delivery/0003-third-vertical-slice.md#completion-evidence)
and [Issue #72](https://github.com/Kentaro-Ono-jp/Portfolio/issues/72).

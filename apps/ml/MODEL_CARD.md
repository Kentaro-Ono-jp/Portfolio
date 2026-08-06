# ReactorFront document-type classifier model card

## Model details

- Name: `reactorfront-document-type`
- Version: `document-type-candidate-v1`
- Artifact schema: deterministic JSON containing vocabulary, linear weights,
  bias, and training metadata
- Expected SHA-256:
  `17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09`
- Selection: reviewed [`promoted-model-v1.json`](evaluation/promoted-model-v1.json)
- Runtime: pinned CPU PyTorch in the `ml-worker` image

## Intended use

This model is a repository-verification artifact for classifying the first
vertical slice's synthetic, single-page, extractable-text PDFs as `invoice` or
`report`. It demonstrates an explicit and reproducible ML lifecycle; it is not
intended for production document decisions.

## Inputs and preprocessing

The worker verifies the source SHA-256, extracts text from exactly one PDF page,
normalizes Unicode with NFKC, lowercases the text, selects ASCII alphanumeric
tokens, and constructs a deterministic bag-of-words vector using the vocabulary
stored in the artifact. Scanned PDFs, OCR, images, encrypted PDFs, empty text,
and multi-page documents are unsupported.

## Training data and algorithm

Training uses exactly the 12 samples assigned to the training split in the
reviewed `reactorfront-synthetic-documents-v1` snapshot, split evenly between
invoices and reports. The candidate-build identity binds those sample IDs, the
snapshot and split digests, the pinned dependency lock, and fixed seed
(`20260719`). Single-thread deterministic CPU settings produce Laplace-smoothed
class/token counts. PyTorch calculates the log probabilities used by a two-class
linear classifier. Parameters are rounded to eight decimal places before
canonical JSON serialization.

The training-data SHA-256 and training accuracy are embedded in the generated
artifact. The controlled fixture set reaches 100% training accuracy. That
number describes only the small synthetic build inputs and is not a real-world
quality claim.

## Evaluation condition

The immutable `reactorfront-synthetic-documents-v1` snapshot contains 18
repository-authored samples in a fixed family-disjoint split: 12 training, two
validation, and four held-out test samples. Every split contains both classes.
Canonical verification reconstructs this model from the original 12 training
snippets, verifies artifact SHA-256, evaluates every held-out sample twice, and
requires both reports to be byte-identical to the committed candidate report.

On the four held-out synthetic samples, `document-type-candidate-v1` processes 4/4 with
no sanitized failure. Its bounded baseline records macro F1 `1.0`, per-class
precision/recall/F1 `1.0`, and mean true-label model score `0.99982216`. The
report records one sanitized accepted outcome per held-out sample so every
published aggregate and gate can be recomputed independently. Its SHA-256 is
`83493ba1053c6252651e64a9afdb424385eb527c1c2ca94cbc99ade0d610d861`.
Runtime CI separately retains real PyTorch inference through repository-
generated invoice and report PDFs.

## Promotion and rollback

The separately versioned `document-type-candidate-v1` artifact is generated
from exactly the accepted 12-sample training split rather than from validation
or test data. Its reviewed build identity binds the dataset and split digests,
training sample IDs, preprocessing and pipeline versions, fixed seed, pinned
`uv.lock` digest, and artifact SHA-256
`17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09`.
The artifact remains generated outside Git history.

The model processes all four held-out samples correctly with macro F1
`1.0`, per-class recall `1.0`, and mean true-label model score `0.99982216`.
Its canonical report SHA-256 is
`83493ba1053c6252651e64a9afdb424385eb527c1c2ca94cbc99ade0d610d861`.
The canonical comparison independently recomputes every absolute and
champion-relative gate and records the candidate as eligible. The reviewed
promotion manifest selects exactly that candidate, report, policy, dataset,
pipeline, artifact, and ontology; the image build and worker readiness both
fail closed when any identity differs. No confidence calibration is fitted, so
the value remains a model score rather than a calibrated probability.

The previous `document-type-v1` artifact remains a reviewed rollback target
through the same manifest schema. Rollback must be another reviewed manifest
change selecting its accepted artifact and champion-baseline report; it cannot
rewrite an earlier prediction, review, audit record, or feedback candidate.

## Limitations and risks

- The vocabulary is intentionally tiny and English-only.
- Confidence is a synthetic demonstration value and is not calibrated for
  production use.
- The held-out set has only four repository-authored synthetic samples; its
  perfect class metrics do not establish external validity or production
  quality.
- PyTorch does not guarantee byte-identical results across arbitrary releases
  or platforms; reproducibility is claimed only for the pinned CPU build path.
- Layout, tables, OCR, handwriting, images, adversarial PDFs, and domain drift
  are not evaluated.
- No fairness, privacy, robustness, or production accuracy claim is made.

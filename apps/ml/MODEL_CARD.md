# ReactorFront document-type classifier model card

## Model details

- Name: `reactorfront-document-type`
- Version: `document-type-v1`
- Artifact schema: deterministic JSON containing vocabulary, linear weights,
  bias, and training metadata
- Expected SHA-256:
  `82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac`
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

Training uses the 12 repository-authored synthetic snippets in
[`data/training.json`](data/training.json), split evenly between invoices and
reports. A fixed seed (`20260719`) and single-thread deterministic CPU settings
produce Laplace-smoothed class/token counts. PyTorch calculates the log
probabilities used by a two-class linear classifier. Parameters are rounded to
eight decimal places before canonical JSON serialization.

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
requires both reports to be byte-identical to the committed baseline.

On the four held-out synthetic samples, `document-type-v1` processes 4/4 with
no sanitized failure. Its bounded baseline records macro F1 `1.0`, per-class
precision/recall/F1 `1.0`, and mean true-label model score `0.99982216`. The
report SHA-256 is
`c6faa19f7a0f697e71cf30d6fa13d7bbe11b708827d2948d673a8ba66ace9b0a`.
Runtime CI separately retains real PyTorch inference through repository-
generated invoice and report PDFs.

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

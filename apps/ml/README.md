# ML application boundary

## Intended responsibility

This area will own model inference, evaluation, and model-specific processing.

## Boundary rules

- Keep preprocessing, inference, postprocessing, and evaluation explicit.
- Expose ML capabilities through a documented service or job interface.
- Do not import web or API implementation internals.
- Record model identity, evaluation conditions, and reproducibility constraints
  when a model is selected.

## Accepted first-slice direction

- Classify a synthetic, single-page text PDF as `invoice` or `report`
- Use Python and PyTorch with explicit preprocessing through evaluation
- Execute inference asynchronously through Celery and RabbitMQ
- Read source objects and publish versioned status/result events without direct
  access to the API-owned PostgreSQL schema
- Support CPU-only canonical CI verification
- Generate the small model artifact reproducibly from repository-owned
  synthetic inputs without committing generated binaries to normal Git history
- Record model version and require the canonical invoice fixture to reach at
  least `0.70` confidence

Production model-quality claims, OCR, image input, and GPU execution are
deliberately outside the first vertical slice.

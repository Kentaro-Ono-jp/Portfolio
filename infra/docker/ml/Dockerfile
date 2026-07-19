FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/apps/ml/.venv/bin:${PATH}"

RUN apt-get update && \
    apt-get install --yes --no-install-recommends ca-certificates libgomp1 && \
    rm -rf /var/lib/apt/lists/*

FROM base AS builder

RUN python -m pip install --no-cache-dir uv==0.11.29

WORKDIR /workspace
COPY apps/ml/pyproject.toml apps/ml/uv.lock apps/ml/README.md /workspace/apps/ml/
COPY apps/ml/src /workspace/apps/ml/src
COPY apps/ml/data /workspace/apps/ml/data
COPY apps/ml/model.expected.sha256 /workspace/apps/ml/model.expected.sha256

RUN uv sync --project /workspace/apps/ml --frozen --no-dev --no-editable && \
    /workspace/apps/ml/.venv/bin/python -m reactorfront_ml.generate_model \
      --training-data /workspace/apps/ml/data/training.json \
      --output /model/model.json \
      --checksum-output /model/model.sha256 && \
    cmp /model/model.sha256 /workspace/apps/ml/model.expected.sha256

FROM base AS runtime

LABEL org.opencontainers.image.title="ReactorFront Portfolio ML worker" \
      org.opencontainers.image.description="CPU PyTorch document classifier and confirmed result publisher" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/Kentaro-Ono-jp/Portfolio"

RUN groupadd --gid 10002 portfolio-ml && \
    useradd --uid 10002 --gid portfolio-ml --no-create-home --home-dir /nonexistent portfolio-ml

WORKDIR /workspace
COPY --from=builder /workspace/apps/ml/.venv /workspace/apps/ml/.venv
COPY --from=builder --chown=10002:10002 /model /opt/reactorfront/model
COPY --chown=10002:10002 apps/ml/MODEL_CARD.md /opt/reactorfront/model/MODEL_CARD.md
COPY --chown=10002:10002 packages/contracts/events /workspace/packages/contracts/events

USER 10002:10002
CMD ["/bin/sh", "-c", "python -m reactorfront_ml.health --check && exec celery -A reactorfront_ml.celery_app:app worker --loglevel=INFO --concurrency=1 --pool=solo"]

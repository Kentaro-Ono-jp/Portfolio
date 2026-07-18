FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/apps/api/.venv/bin:${PATH}"

RUN groupadd --gid 10001 portfolio && \
    useradd --uid 10001 --gid portfolio --no-create-home --home-dir /nonexistent portfolio && \
    python -m pip install --no-cache-dir uv==0.11.29

WORKDIR /workspace
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md /workspace/apps/api/
COPY apps/api/src /workspace/apps/api/src
COPY apps/api/alembic.ini /workspace/apps/api/alembic.ini
COPY apps/api/alembic /workspace/apps/api/alembic
COPY packages/contracts/events /workspace/packages/contracts/events

RUN uv sync --project /workspace/apps/api --frozen --no-dev --no-editable && \
    /workspace/apps/api/.venv/bin/python -c "import reactorfront_api.main" && \
    chown -R portfolio:portfolio /workspace

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "reactorfront_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Integration tests

This directory will contain tests that verify interactions between two or more
service boundaries without exercising the full user journey.

The first slice will verify FastAPI, PostgreSQL, MinIO, RabbitMQ, and the
Celery/PyTorch worker through public service boundaries. Fixtures must be
repository-owned synthetic data. The final runner command will be exposed
through the shared root verification entrypoint.

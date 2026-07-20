# Integration tests

This directory will contain tests that verify interactions between two or more
service boundaries without exercising the full user journey.

The first slice verifies FastAPI, PostgreSQL, MinIO, RabbitMQ, and the
Celery/PyTorch worker through public service boundaries. The current proof also
crosses the API-owned `api-events` boundary and checks atomic receipts,
processing/completed/failed persistence, logical duplicate handling, ordering
recovery, poison rejection, and first-terminal preservation. Fixtures are
repository-owned synthetic data. The runner command is exposed through the
shared root verification entrypoint.

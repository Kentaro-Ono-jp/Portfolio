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

The authentication-foundation increment additionally proves a real Dex
Authorization Code and PKCE token path, validation from inside the API
container through its OIDC backchannel, stable `(issuer, subject)` principal
resolution, and a populated first-slice migration without fabricated human
attribution.

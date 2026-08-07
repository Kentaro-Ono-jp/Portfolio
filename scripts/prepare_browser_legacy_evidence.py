from __future__ import annotations

import json
import os
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine, text

API_SYSTEM_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000002")
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://portfolio:portfolio-local-password@127.0.0.1:55432/portfolio"
)
DOCUMENT_ID = UUID("10000000-0000-4000-8000-000000000087")
JOB_ID = UUID("20000000-0000-4000-8000-000000000087")
SUBMITTED_AUDIT_ID = UUID("30000000-0000-4000-8000-000000000087")
COMPLETED_AUDIT_ID = UUID("40000000-0000-4000-8000-000000000087")
SUBMITTED_CAUSATION_ID = UUID("50000000-0000-4000-8000-000000000087")
COMPLETED_CAUSATION_ID = UUID("60000000-0000-4000-8000-000000000087")
SUBMITTED_CORRELATION_ID = UUID("70000000-0000-4000-8000-000000000087")
COMPLETED_CORRELATION_ID = UUID("80000000-0000-4000-8000-000000000087")
CREATED_AT = datetime(2026, 8, 7, 11, 0, tzinfo=UTC)


def prepare_fixture(database_url: str, *, owner_document_id: UUID) -> dict[str, str]:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            principal_id = connection.execute(
                text(
                    "SELECT p.id FROM principals p "
                    "JOIN documents d ON d.submitted_by_principal_id = p.id "
                    "WHERE d.id = :owner_document_id AND p.kind = 'oidc'"
                ),
                {"owner_document_id": owner_document_id},
            ).scalar_one_or_none()
            if principal_id is None:
                raise RuntimeError(
                    "The authenticated synthetic browser principal is unavailable."
                )

            for statement in (
                "DELETE FROM idempotency_records WHERE target_document_id = :document_id",
                "DELETE FROM audit_events WHERE document_id = :document_id",
                "DELETE FROM review_decisions WHERE document_id = :document_id",
                "DELETE FROM result_event_receipts WHERE document_id = :document_id",
                "DELETE FROM outbox_events WHERE aggregate_id = :job_id",
                "DELETE FROM processing_jobs WHERE id = :job_id",
                "DELETE FROM documents WHERE id = :document_id",
            ):
                connection.execute(
                    text(statement),
                    {"document_id": DOCUMENT_ID, "job_id": JOB_ID},
                )

            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(id, submitted_by_principal_id, original_filename, object_key, "
                    "sha256, content_type, size_bytes, created_at) VALUES "
                    "(:id, :principal_id, :filename, :object_key, :sha256, "
                    ":content_type, :size_bytes, :created_at)"
                ),
                {
                    "id": DOCUMENT_ID,
                    "principal_id": principal_id,
                    "filename": "legacy-evidence.pdf",
                    "object_key": f"documents/{DOCUMENT_ID}/source.pdf",
                    "sha256": "f" * 64,
                    "content_type": "application/pdf",
                    "size_bytes": 42,
                    "created_at": CREATED_AT,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO processing_jobs "
                    "(id, document_id, status, attempt_count, model_version, "
                    "predicted_class, confidence, failure_code, created_at, "
                    "started_at, completed_at) VALUES "
                    "(:id, :document_id, 'completed', 1, 'document-type-v1', "
                    "'report', 0.9000, NULL, :created_at, :started_at, :completed_at)"
                ),
                {
                    "id": JOB_ID,
                    "document_id": DOCUMENT_ID,
                    "created_at": CREATED_AT,
                    "started_at": CREATED_AT + timedelta(seconds=1),
                    "completed_at": CREATED_AT + timedelta(seconds=2),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(id, action, actor_principal_id, document_id, job_id, review_id, "
                    "correlation_id, causation_id, occurred_at, details_version, details) "
                    "VALUES "
                    "(:submitted_id, 'document.submitted', :principal_id, :document_id, "
                    ":job_id, NULL, :submitted_correlation_id, :submitted_causation_id, "
                    ":submitted_at, 1, CAST('{}' AS jsonb)), "
                    "(:completed_id, 'processing.completed', :api_principal_id, "
                    ":document_id, :job_id, NULL, :completed_correlation_id, "
                    ":completed_causation_id, :completed_at, 1, CAST('{}' AS jsonb))"
                ),
                {
                    "submitted_id": SUBMITTED_AUDIT_ID,
                    "completed_id": COMPLETED_AUDIT_ID,
                    "principal_id": principal_id,
                    "api_principal_id": API_SYSTEM_PRINCIPAL_ID,
                    "document_id": DOCUMENT_ID,
                    "job_id": JOB_ID,
                    "submitted_correlation_id": SUBMITTED_CORRELATION_ID,
                    "completed_correlation_id": COMPLETED_CORRELATION_ID,
                    "submitted_causation_id": SUBMITTED_CAUSATION_ID,
                    "completed_causation_id": COMPLETED_CAUSATION_ID,
                    "submitted_at": CREATED_AT,
                    "completed_at": CREATED_AT + timedelta(seconds=2),
                },
            )
    finally:
        engine.dispose()
    return {"documentId": str(DOCUMENT_ID), "jobId": str(JOB_ID)}


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--owner-document-id", type=UUID, required=True)
    arguments = parser.parse_args()
    database_url = os.environ.get("PORTFOLIO_DATABASE_URL", DEFAULT_DATABASE_URL)
    print(
        json.dumps(
            prepare_fixture(
                database_url,
                owner_document_id=arguments.owner_document_id,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

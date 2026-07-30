from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from reactorfront_api.persistence import (
    LEGACY_SYSTEM_PRINCIPAL_ID,
    LEGACY_SYSTEM_PRINCIPAL_KEY,
)
from reactorfront_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"
V1_REVISION = "20260720_0002"
HEAD_REVISION = "20260731_0003"
DOCUMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
JOB_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OUTBOX_EVENT_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
RESULT_EVENT_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
CORRELATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()
    finally:
        engine.dispose()


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPOSITORY_ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def prepare_v1_fixture(database_url: str) -> None:
    engine = create_engine(database_url)
    requested_payload = {
        "eventId": str(OUTBOX_EVENT_ID),
        "eventType": "document.processing.requested.v1",
        "occurredAt": "2026-07-20T00:00:00Z",
        "correlationId": str(CORRELATION_ID),
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "objectKey": f"documents/{DOCUMENT_ID}/source.pdf",
        "sourceSha256": "a" * 64,
    }
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE result_event_receipts, outbox_events, processing_jobs, "
                    "documents RESTART IDENTITY CASCADE"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(id, original_filename, object_key, sha256, content_type, "
                    "size_bytes, created_at) "
                    "VALUES (:id, :filename, :object_key, :sha256, :content_type, "
                    ":size_bytes, :created_at)"
                ),
                {
                    "id": DOCUMENT_ID,
                    "filename": "legacy-report.pdf",
                    "object_key": f"documents/{DOCUMENT_ID}/source.pdf",
                    "sha256": "a" * 64,
                    "content_type": "application/pdf",
                    "size_bytes": 42,
                    "created_at": "2026-07-20T00:00:00Z",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO processing_jobs "
                    "(id, document_id, status, attempt_count, model_version, "
                    "predicted_class, confidence, failure_code, created_at, "
                    "started_at, completed_at) "
                    "VALUES (:id, :document_id, 'completed', 1, 'document-type-v1', "
                    "'report', 0.9000, NULL, :created_at, :started_at, :completed_at)"
                ),
                {
                    "id": JOB_ID,
                    "document_id": DOCUMENT_ID,
                    "created_at": "2026-07-20T00:00:00Z",
                    "started_at": "2026-07-20T00:00:01Z",
                    "completed_at": "2026-07-20T00:00:02Z",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO outbox_events "
                    "(event_id, event_type, aggregate_id, payload, created_at, "
                    "published_at, leased_until, lease_owner, attempt_count, last_error) "
                    "VALUES (:event_id, 'document.processing.requested.v1', :job_id, "
                    "CAST(:payload AS jsonb), :created_at, :published_at, NULL, NULL, 1, NULL)"
                ),
                {
                    "event_id": OUTBOX_EVENT_ID,
                    "job_id": JOB_ID,
                    "payload": json.dumps(requested_payload, separators=(",", ":")),
                    "created_at": "2026-07-20T00:00:00Z",
                    "published_at": "2026-07-20T00:00:01Z",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO result_event_receipts "
                    "(event_id, event_type, document_id, job_id, logical_payload_sha256, "
                    "occurred_at, received_at) "
                    "VALUES (:event_id, 'document.processing.completed.v1', :document_id, "
                    ":job_id, :digest, :occurred_at, :received_at)"
                ),
                {
                    "event_id": RESULT_EVENT_ID,
                    "document_id": DOCUMENT_ID,
                    "job_id": JOB_ID,
                    "digest": "b" * 64,
                    "occurred_at": "2026-07-20T00:00:02Z",
                    "received_at": "2026-07-20T00:00:03Z",
                },
            )
    finally:
        engine.dispose()


def verify_upgraded_fixture(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            counts = {
                table_name: int(
                    connection.execute(
                        text(f"SELECT count(*) FROM {table_name}")
                    ).scalar_one()
                )
                for table_name in (
                    "documents",
                    "processing_jobs",
                    "outbox_events",
                    "result_event_receipts",
                )
            }
            if set(counts.values()) != {1}:
                raise RuntimeError(f"Populated migration changed row counts: {counts}")
            document = connection.execute(
                text(
                    "SELECT original_filename, object_key, sha256, content_type, "
                    "size_bytes, submitted_by_principal_id "
                    "FROM documents WHERE id = :document_id"
                ),
                {"document_id": DOCUMENT_ID},
            ).one()
            if tuple(document) != (
                "legacy-report.pdf",
                f"documents/{DOCUMENT_ID}/source.pdf",
                "a" * 64,
                "application/pdf",
                42,
                LEGACY_SYSTEM_PRINCIPAL_ID,
            ):
                raise RuntimeError(
                    "The migrated document identity or source metadata changed."
                )
            legacy = connection.execute(
                text(
                    "SELECT kind, issuer, subject, system_key FROM principals "
                    "WHERE id = :principal_id"
                ),
                {"principal_id": LEGACY_SYSTEM_PRINCIPAL_ID},
            ).one()
            if tuple(legacy) != (
                "system",
                None,
                None,
                LEGACY_SYSTEM_PRINCIPAL_KEY,
            ):
                raise RuntimeError("The controlled legacy principal is invalid.")
            job = connection.execute(
                text(
                    "SELECT status, model_version, predicted_class, confidence "
                    "FROM processing_jobs WHERE id = :job_id"
                ),
                {"job_id": JOB_ID},
            ).one()
            if (
                job.status != "completed"
                or job.model_version != "document-type-v1"
                or job.predicted_class != "report"
                or float(job.confidence) != 0.9
            ):
                raise RuntimeError("Immutable machine-result evidence changed.")
            connection.execute(
                text(
                    "TRUNCATE result_event_receipts, outbox_events, processing_jobs, "
                    "documents RESTART IDENTITY CASCADE"
                )
            )
        return {
            "fromRevision": V1_REVISION,
            "toRevision": HEAD_REVISION,
            "preservedRowCounts": counts,
            "legacyPrincipalKind": "system",
            "syntheticHumanAttribution": False,
        }
    finally:
        engine.dispose()


def main() -> int:
    settings = Settings()
    config = alembic_config(settings.database_url)
    revision = current_revision(settings.database_url)
    if revision is None:
        command.upgrade(config, V1_REVISION)
    elif revision == HEAD_REVISION:
        command.downgrade(config, V1_REVISION)
    elif revision != V1_REVISION:
        raise RuntimeError(f"Unexpected migration starting revision: {revision}")

    prepare_v1_fixture(settings.database_url)
    command.upgrade(config, "head")
    if current_revision(settings.database_url) != HEAD_REVISION:
        raise RuntimeError("Principal migration did not reach the expected head.")
    evidence = verify_upgraded_fixture(settings.database_url)
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / "principal-migration-proof.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Populated first-slice data migrated without loss or human attribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

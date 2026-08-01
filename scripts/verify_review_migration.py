from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from reactorfront_api.persistence import (
    API_SYSTEM_PRINCIPAL_ID,
    API_SYSTEM_PRINCIPAL_KEY,
    LEGACY_SYSTEM_PRINCIPAL_ID,
)
from reactorfront_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"
BASE_REVISION = "20260731_0003"
HEAD_REVISION = "20260801_0004"
DOCUMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
JOB_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OUTBOX_EVENT_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
RESULT_EVENT_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
CORRELATION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPOSITORY_ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def prepare_foundation_fixture(database_url: str) -> None:
    engine = create_engine(database_url)
    requested_payload = {
        "eventId": str(OUTBOX_EVENT_ID),
        "eventType": "document.processing.requested.v1",
        "occurredAt": "2026-08-01T00:00:00Z",
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
                    "(id, submitted_by_principal_id, original_filename, object_key, "
                    "sha256, content_type, size_bytes, created_at) "
                    "VALUES (:id, :principal_id, :filename, :object_key, :sha256, "
                    ":content_type, :size_bytes, :created_at)"
                ),
                {
                    "id": DOCUMENT_ID,
                    "principal_id": LEGACY_SYSTEM_PRINCIPAL_ID,
                    "filename": "preserved-report.pdf",
                    "object_key": f"documents/{DOCUMENT_ID}/source.pdf",
                    "sha256": "a" * 64,
                    "content_type": "application/pdf",
                    "size_bytes": 42,
                    "created_at": "2026-08-01T00:00:00Z",
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
                    "created_at": "2026-08-01T00:00:00Z",
                    "started_at": "2026-08-01T00:00:01Z",
                    "completed_at": "2026-08-01T00:00:02Z",
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
                    "created_at": "2026-08-01T00:00:00Z",
                    "published_at": "2026-08-01T00:00:01Z",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO result_event_receipts "
                    "(event_id, event_type, document_id, job_id, logical_payload_sha256, "
                    "occurred_at, received_at) VALUES (:event_id, "
                    "'document.processing.completed.v1', :document_id, :job_id, "
                    ":digest, :occurred_at, :received_at)"
                ),
                {
                    "event_id": RESULT_EVENT_ID,
                    "document_id": DOCUMENT_ID,
                    "job_id": JOB_ID,
                    "digest": "b" * 64,
                    "occurred_at": "2026-08-01T00:00:02Z",
                    "received_at": "2026-08-01T00:00:03Z",
                },
            )
    finally:
        engine.dispose()


def verify_preserved_fixture(database_url: str, *, expect_review_tables: bool) -> None:
    engine = create_engine(database_url)
    try:
        table_names = set(inspect(engine).get_table_names())
        review_tables = {"review_decisions", "idempotency_records", "audit_events"}
        if expect_review_tables != review_tables.issubset(table_names):
            raise RuntimeError("Review migration table state is inconsistent.")
        with engine.connect() as connection:
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
                raise RuntimeError(f"Migration changed existing row counts: {counts}")
            if expect_review_tables:
                new_counts = {
                    table_name: int(
                        connection.execute(
                            text(f"SELECT count(*) FROM {table_name}")
                        ).scalar_one()
                    )
                    for table_name in review_tables
                }
                if set(new_counts.values()) != {0}:
                    raise RuntimeError(
                        "Migration fabricated review or historical audit state: "
                        f"{new_counts}"
                    )
                system_identity = connection.execute(
                    text(
                        "SELECT kind, system_key FROM principals WHERE id = :principal_id"
                    ),
                    {"principal_id": API_SYSTEM_PRINCIPAL_ID},
                ).one()
                if tuple(system_identity) != ("system", API_SYSTEM_PRINCIPAL_KEY):
                    raise RuntimeError(
                        "The controlled API system principal is invalid."
                    )
    finally:
        engine.dispose()


def cleanup(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE audit_events, idempotency_records, review_decisions, "
                    "result_event_receipts, outbox_events, processing_jobs, documents "
                    "RESTART IDENTITY CASCADE"
                )
            )
    finally:
        engine.dispose()


def restore_head_and_cleanup(database_url: str, config: Config) -> None:
    if current_revision(database_url) != HEAD_REVISION:
        command.upgrade(config, HEAD_REVISION)
    cleanup(database_url)


def main() -> int:
    settings = Settings()
    config = alembic_config(settings.database_url)
    revision = current_revision(settings.database_url)
    if revision is None:
        command.upgrade(config, BASE_REVISION)
    elif revision == HEAD_REVISION:
        command.downgrade(config, BASE_REVISION)
    elif revision != BASE_REVISION:
        raise RuntimeError(f"Unexpected migration starting revision: {revision}")

    primary_error: BaseException | None = None
    try:
        prepare_foundation_fixture(settings.database_url)
        command.upgrade(config, HEAD_REVISION)
        verify_preserved_fixture(settings.database_url, expect_review_tables=True)
        command.downgrade(config, BASE_REVISION)
        verify_preserved_fixture(settings.database_url, expect_review_tables=False)
        command.upgrade(config, HEAD_REVISION)
        verify_preserved_fixture(settings.database_url, expect_review_tables=True)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            restore_head_and_cleanup(settings.database_url, config)
        except Exception as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"Runtime restoration also failed: {cleanup_error!r}"
            )

    evidence = {
        "fromRevision": BASE_REVISION,
        "toRevision": HEAD_REVISION,
        "preservedExistingRows": True,
        "forwardAndBackwardExplicit": True,
        "fabricatedHistoricalAuditEvents": False,
        "apiSystemPrincipal": API_SYSTEM_PRINCIPAL_KEY,
    }
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / "review-migration-proof.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Review and audit schema migrated forward and backward without data loss.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

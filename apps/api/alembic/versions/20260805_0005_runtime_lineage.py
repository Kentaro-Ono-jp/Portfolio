"""Persist immutable measured runtime model lineage.

Revision ID: 20260805_0005
Revises: 20260801_0004
Create Date: 2026-08-05 23:15:00+09:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0005"
down_revision: str | None = "20260801_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, length in (
        ("dataset_version", 128),
        ("dataset_sha256", 64),
        ("preprocessing_version", 128),
        ("pipeline_version", 128),
        ("artifact_sha256", 64),
        ("evaluation_policy_version", 128),
        ("evaluation_policy_sha256", 64),
        ("evaluation_report_sha256", 64),
    ):
        op.add_column(
            "processing_jobs",
            sa.Column(name, sa.String(length=length), nullable=True),
        )

    op.create_check_constraint(
        "ck_processing_jobs_dataset_sha256",
        "processing_jobs",
        "dataset_sha256 IS NULL OR dataset_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "ck_processing_jobs_artifact_sha256",
        "processing_jobs",
        "artifact_sha256 IS NULL OR artifact_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "ck_processing_jobs_evaluation_policy_sha256",
        "processing_jobs",
        "evaluation_policy_sha256 IS NULL OR evaluation_policy_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "ck_processing_jobs_evaluation_report_sha256",
        "processing_jobs",
        "evaluation_report_sha256 IS NULL OR evaluation_report_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "ck_processing_jobs_model_evidence_shape",
        "processing_jobs",
        "(dataset_version IS NULL AND dataset_sha256 IS NULL "
        "AND preprocessing_version IS NULL AND pipeline_version IS NULL "
        "AND artifact_sha256 IS NULL AND evaluation_policy_version IS NULL "
        "AND evaluation_policy_sha256 IS NULL AND evaluation_report_sha256 IS NULL) OR "
        "(status = 'completed' AND dataset_version IS NOT NULL "
        "AND dataset_sha256 IS NOT NULL AND preprocessing_version IS NOT NULL "
        "AND pipeline_version IS NOT NULL AND artifact_sha256 IS NOT NULL "
        "AND evaluation_policy_version IS NOT NULL "
        "AND evaluation_policy_sha256 IS NOT NULL "
        "AND evaluation_report_sha256 IS NOT NULL)",
    )

    op.drop_constraint(
        "ck_result_event_receipts_type",
        "result_event_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_result_event_receipts_type",
        "result_event_receipts",
        "event_type IN ('document.processing.started.v1', "
        "'document.processing.completed.v1', 'document.processing.completed.v2', "
        "'document.processing.failed.v1')",
    )
    op.drop_constraint("ck_audit_events_details_version", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_details_version",
        "audit_events",
        "details_version = 1 OR (details_version = 2 AND action = 'processing.completed')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    measured_exists = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM processing_jobs WHERE dataset_version IS NOT NULL)")
    ).scalar_one()
    if measured_exists:
        raise RuntimeError("Refusing to discard persisted measured model lineage during downgrade")

    op.drop_constraint("ck_audit_events_details_version", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_details_version",
        "audit_events",
        "details_version = 1",
    )
    op.drop_constraint(
        "ck_result_event_receipts_type",
        "result_event_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_result_event_receipts_type",
        "result_event_receipts",
        "event_type IN ('document.processing.started.v1', "
        "'document.processing.completed.v1', 'document.processing.failed.v1')",
    )

    for constraint in (
        "ck_processing_jobs_model_evidence_shape",
        "ck_processing_jobs_evaluation_report_sha256",
        "ck_processing_jobs_evaluation_policy_sha256",
        "ck_processing_jobs_artifact_sha256",
        "ck_processing_jobs_dataset_sha256",
    ):
        op.drop_constraint(constraint, "processing_jobs", type_="check")
    for column in (
        "evaluation_report_sha256",
        "evaluation_policy_sha256",
        "evaluation_policy_version",
        "artifact_sha256",
        "pipeline_version",
        "preprocessing_version",
        "dataset_sha256",
        "dataset_version",
    ):
        op.drop_column("processing_jobs", column)

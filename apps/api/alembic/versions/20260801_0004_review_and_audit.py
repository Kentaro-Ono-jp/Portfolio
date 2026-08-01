"""Create immutable review decisions, idempotency receipts, and product audit events.

Revision ID: 20260801_0004
Revises: 20260731_0003
Create Date: 2026-08-01 12:45:00+09:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260801_0004"
down_revision: str | None = "20260731_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_SYSTEM_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000002")
API_SYSTEM_PRINCIPAL_KEY = "api-processing"


def upgrade() -> None:
    principals = sa.table(
        "principals",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("kind", sa.String()),
        sa.column("issuer", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("system_key", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        principals.insert().values(
            id=API_SYSTEM_PRINCIPAL_ID,
            kind="system",
            issuer=None,
            subject=None,
            system_key=API_SYSTEM_PRINCIPAL_KEY,
            created_at=sa.func.now(),
        )
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_classification", sa.String(length=32), nullable=False),
        sa.Column("final_classification", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_version", sa.Integer(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "machine_classification IN ('invoice', 'report')",
            name="ck_review_decisions_machine_classification",
        ),
        sa.CheckConstraint(
            "final_classification IN ('invoice', 'report')",
            name="ck_review_decisions_final_classification",
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'corrected')",
            name="ck_review_decisions_status",
        ),
        sa.CheckConstraint(
            "review_version = 1",
            name="ck_review_decisions_version",
        ),
        sa.CheckConstraint(
            "(status = 'approved' AND machine_classification = final_classification) OR "
            "(status = 'corrected' AND machine_classification <> final_classification)",
            name="ck_review_decisions_status_matches_classification",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_review_decisions_document_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["processing_jobs.id"],
            name="fk_review_decisions_job_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_principal_id"],
            ["principals.id"],
            name="fk_review_decisions_reviewer_principal_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_review_decisions_job_id"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("review_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_digest ~ '^[a-f0-9]{64}$'",
            name="ck_idempotency_records_request_digest",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["principals.id"],
            name="fk_idempotency_records_principal_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_document_id"],
            ["documents.id"],
            name="fk_idempotency_records_target_document_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_decision_id"],
            ["review_decisions.id"],
            name="fk_idempotency_records_review_decision_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_namespace",
        ),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_version", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "action IN ('document.submitted', 'processing.completed', "
            "'processing.failed', 'review.approved', 'review.corrected')",
            name="ck_audit_events_action",
        ),
        sa.CheckConstraint(
            "details_version = 1",
            name="ck_audit_events_details_version",
        ),
        sa.ForeignKeyConstraint(
            ["actor_principal_id"],
            ["principals.id"],
            name="fk_audit_events_actor_principal_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_audit_events_document_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["processing_jobs.id"],
            name="fk_audit_events_job_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["review_decisions.id"],
            name="fk_audit_events_review_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action", "causation_id", name="uq_audit_events_causation"),
    )
    op.create_index(
        "ix_audit_events_document_order",
        "audit_events",
        ["document_id", "occurred_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_document_order", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("idempotency_records")
    op.drop_table("review_decisions")
    op.execute(
        sa.text("DELETE FROM principals WHERE id = :principal_id").bindparams(
            principal_id=API_SYSTEM_PRINCIPAL_ID
        )
    )

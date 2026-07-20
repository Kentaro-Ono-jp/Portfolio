"""Create the API-owned result-event receipt boundary.

Revision ID: 20260720_0002
Revises: 20260718_0001
Create Date: 2026-07-20 08:30:00+09:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260720_0002"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "result_event_receipts",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("logical_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('document.processing.started.v1', "
            "'document.processing.completed.v1', 'document.processing.failed.v1')",
            name="ck_result_event_receipts_type",
        ),
        sa.CheckConstraint(
            "logical_payload_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_result_event_receipts_payload_sha256",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_result_event_receipts_job",
        "result_event_receipts",
        ["job_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_result_event_receipts_job", table_name="result_event_receipts")
    op.drop_table("result_event_receipts")

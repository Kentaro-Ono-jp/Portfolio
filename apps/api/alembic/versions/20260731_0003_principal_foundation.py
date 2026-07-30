"""Create the API-owned principal and document-ownership foundation.

Revision ID: 20260731_0003
Revises: 20260720_0002
Create Date: 2026-07-31 01:00:00+09:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260731_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_SYSTEM_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000001")
LEGACY_SYSTEM_PRINCIPAL_KEY = "legacy-first-slice"


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("issuer", sa.String(length=2048), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("system_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(kind = 'oidc' AND issuer IS NOT NULL AND length(issuer) > 0 "
            "AND subject IS NOT NULL AND length(subject) > 0 AND system_key IS NULL) OR "
            "(kind = 'system' AND issuer IS NULL AND subject IS NULL "
            "AND system_key IS NOT NULL AND length(system_key) > 0)",
            name="ck_principals_identity_shape",
        ),
        sa.CheckConstraint(
            "kind IN ('oidc', 'system')",
            name="ck_principals_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_principals_oidc_identity",
        ),
        sa.UniqueConstraint(
            "system_key",
            name="uq_principals_system_key",
        ),
    )
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
            id=LEGACY_SYSTEM_PRINCIPAL_ID,
            kind="system",
            issuer=None,
            subject=None,
            system_key=LEGACY_SYSTEM_PRINCIPAL_KEY,
            created_at=sa.func.now(),
        )
    )
    op.add_column(
        "documents",
        sa.Column(
            "submitted_by_principal_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE documents SET submitted_by_principal_id = :principal_id "
            "WHERE submitted_by_principal_id IS NULL"
        ).bindparams(principal_id=LEGACY_SYSTEM_PRINCIPAL_ID)
    )
    op.alter_column(
        "documents",
        "submitted_by_principal_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_documents_submitted_by_principal_id",
        "documents",
        "principals",
        ["submitted_by_principal_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_submitted_by_principal_id",
        "documents",
        type_="foreignkey",
    )
    op.drop_column("documents", "submitted_by_principal_id")
    op.drop_table("principals")

"""phase 4 multitenancy and background jobs

Revision ID: 0004_phase4_multitenancy
Revises: 0003_phase3_memory
Create Date: 2026-06-18 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_phase4_multitenancy"
down_revision = "0003_phase3_memory"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    columns = inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _index_exists(table_name: str, index_name: str) -> bool:
    indexes = inspect(op.get_bind()).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _add_organization_email_domain() -> None:
    if _table_exists("organizations") and not _column_exists("organizations", "email_domain"):
        op.add_column("organizations", sa.Column("email_domain", sa.String(length=255), nullable=True))
    if _table_exists("organizations") and not _index_exists("organizations", "ix_organizations_email_domain"):
        op.create_index("ix_organizations_email_domain", "organizations", ["email_domain"], unique=True)


def _drop_organization_email_domain() -> None:
    if _table_exists("organizations") and _index_exists("organizations", "ix_organizations_email_domain"):
        op.drop_index("ix_organizations_email_domain", table_name="organizations")
    if _table_exists("organizations") and _column_exists("organizations", "email_domain"):
        op.drop_column("organizations", "email_domain")


def _create_background_jobs() -> None:
    if not _table_exists("background_jobs"):
        op.create_table(
            "background_jobs",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("job_type", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency_key"),
        )
    if _table_exists("background_jobs") and not _index_exists("background_jobs", "ix_background_jobs_organization_id_user_id"):
        op.create_index(
            "ix_background_jobs_organization_id_user_id",
            "background_jobs",
            ["organization_id", "user_id"],
        )
    if _table_exists("background_jobs") and not _index_exists("background_jobs", "ix_background_jobs_status"):
        op.create_index("ix_background_jobs_status", "background_jobs", ["status"])


def _drop_background_jobs() -> None:
    if _table_exists("background_jobs") and _index_exists("background_jobs", "ix_background_jobs_status"):
        op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    if _table_exists("background_jobs") and _index_exists("background_jobs", "ix_background_jobs_organization_id_user_id"):
        op.drop_index("ix_background_jobs_organization_id_user_id", table_name="background_jobs")
    if _table_exists("background_jobs"):
        op.drop_table("background_jobs")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        existing_columns = {column["name"] for column in inspect(bind).get_columns("organizations")}
        existing_indexes = {index["name"] for index in inspect(bind).get_indexes("organizations")}
        with op.batch_alter_table("organizations") as batch_op:
            if "email_domain" not in existing_columns:
                batch_op.add_column(sa.Column("email_domain", sa.String(length=255), nullable=True))
            if "ix_organizations_email_domain" not in existing_indexes:
                batch_op.create_index("ix_organizations_email_domain", ["email_domain"], unique=True)
    else:
        _add_organization_email_domain()

    _create_background_jobs()


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    _drop_background_jobs()

    if dialect == "sqlite":
        existing_columns = {column["name"] for column in inspect(bind).get_columns("organizations")}
        existing_indexes = {index["name"] for index in inspect(bind).get_indexes("organizations")}
        with op.batch_alter_table("organizations") as batch_op:
            if "ix_organizations_email_domain" in existing_indexes:
                batch_op.drop_index("ix_organizations_email_domain")
            if "email_domain" in existing_columns:
                batch_op.drop_column("email_domain")
    else:
        _drop_organization_email_domain()

"""Create jobs table.

Revision ID: 20261110_0001
Revises:
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261110_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

job_type_enum = postgresql.ENUM(
    "internship",
    "full-time",
    name="job_type_enum",
    create_type=False,
)
job_status_enum = postgresql.ENUM(
    "active",
    "expired",
    name="job_status_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    job_type_enum.create(bind, checkfirst=True)
    job_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("job_type", job_type_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            job_status_enum,
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    job_status_enum.drop(op.get_bind(), checkfirst=True)
    job_type_enum.drop(op.get_bind(), checkfirst=True)

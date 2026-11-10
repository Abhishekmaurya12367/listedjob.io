"""Add job search and filter indexes.

Revision ID: 20261111_0002
Revises: 20261110_0001
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20261111_0002"
down_revision: Union[str, None] = "20261110_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_jobs_city", "jobs", ["city"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"])
    op.execute(
        """
        CREATE INDEX ix_jobs_search
        ON jobs
        USING GIN (
            to_tsvector(
                'english',
                coalesce(title, '') || ' ' || coalesce(company, '') || ' ' ||
                coalesce(description, '')
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_jobs_search")
    op.drop_index("ix_jobs_posted_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_index("ix_jobs_city", table_name="jobs")

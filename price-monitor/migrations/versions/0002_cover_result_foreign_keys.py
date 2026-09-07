"""Add covering indexes for result foreign keys.

Revision ID: 0002_cover_result_foreign_keys
Revises: 0001_initial_schema
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_cover_result_foreign_keys"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_scraper_health_last_scrape_result_id",
        "scraper_health",
        ["last_scrape_result_id"],
    )
    op.create_index(
        "ix_repair_attempts_trigger_scrape_result_id",
        "repair_attempts",
        ["trigger_scrape_result_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repair_attempts_trigger_scrape_result_id",
        table_name="repair_attempts",
    )
    op.drop_index(
        "ix_scraper_health_last_scrape_result_id",
        table_name="scraper_health",
    )

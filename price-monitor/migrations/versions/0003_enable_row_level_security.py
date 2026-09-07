"""Enable row-level security on every public application table.

Revision ID: 0003_enable_row_level_security
Revises: 0002_cover_result_foreign_keys
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_enable_row_level_security"
down_revision: str | None = "0002_cover_result_foreign_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "alembic_version",
    "customers",
    "competitors",
    "products",
    "competitor_products",
    "scrape_results",
    "price_history",
    "repair_attempts",
    "scraper_health",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TABLES):
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')

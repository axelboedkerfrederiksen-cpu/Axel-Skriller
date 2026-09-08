"""Add durable product price-change alert rules.

Revision ID: 0004_alert_rules
Revises: 0003_enable_row_level_security
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_alert_rules"
down_revision: str | None = "0003_enable_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    uuid_type = sa.Uuid(as_uuid=True)

    op.create_table(
        "alert_rules",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column("product_id", uuid_type, nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("threshold_percent", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            timestamp,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            timestamp,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('decrease', 'increase', 'either')",
            name=op.f("ck_alert_rules_direction_valid"),
        ),
        sa.CheckConstraint(
            "threshold_percent > 0 AND threshold_percent <= 10000",
            name=op.f("ck_alert_rules_threshold_percent_range"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_alert_rules_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_alert_rules_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
    )
    op.create_index(
        "ix_alert_rules_customer_active",
        "alert_rules",
        ["customer_id", "is_active"],
    )
    op.create_index("ix_alert_rules_product_id", "alert_rules", ["product_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE public."alert_rules" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_index("ix_alert_rules_product_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_customer_active", table_name="alert_rules")
    op.drop_table("alert_rules")

"""Create the initial price-monitor schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    uuid_type = sa.Uuid(as_uuid=True)
    money = sa.Numeric(18, 4)

    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("webshop_url", sa.Text(), nullable=False),
        sa.Column("default_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("timezone", sa.String(length=100), server_default="UTC", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", uuid_type, nullable=False),
        sa.Column(
            "created_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "length(default_currency) = 3 AND default_currency = upper(default_currency)",
            name=op.f("ck_customers_default_currency_iso_code"),
        ),
        sa.CheckConstraint("length(timezone) > 0", name=op.f("ck_customers_timezone_not_empty")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("slug", name="uq_customers_slug"),
    )

    op.create_table(
        "competitors",
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("adapter_key", sa.String(length=200), nullable=False),
        sa.Column(
            "fetch_mode",
            _enum("fetch_mode", "http", "browser"),
            server_default="http",
            nullable=False,
        ),
        sa.Column(
            "schedule_interval_seconds",
            sa.Integer(),
            server_default=sa.text("3600"),
            nullable=False,
        ),
        sa.Column(
            "min_request_interval_ms",
            sa.Integer(),
            server_default=sa.text("1000"),
            nullable=False,
        ),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("15"), nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("expected_currency", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "active_scraper_revision",
            sa.String(length=100),
            server_default="initial",
            nullable=False,
        ),
        sa.Column("previous_scraper_revision", sa.String(length=100), nullable=True),
        sa.Column("id", uuid_type, nullable=False),
        sa.Column(
            "created_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "expected_currency IS NULL OR "
            "(length(expected_currency) = 3 AND expected_currency = upper(expected_currency))",
            name=op.f("ck_competitors_expected_currency_iso_code"),
        ),
        sa.CheckConstraint("max_retries >= 0", name=op.f("ck_competitors_max_retries_nonnegative")),
        sa.CheckConstraint(
            "min_request_interval_ms >= 0",
            name=op.f("ck_competitors_request_interval_nonnegative"),
        ),
        sa.CheckConstraint(
            "schedule_interval_seconds > 0",
            name=op.f("ck_competitors_schedule_interval_positive"),
        ),
        sa.CheckConstraint("timeout_seconds > 0", name=op.f("ck_competitors_timeout_positive")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_competitors_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competitors")),
        sa.UniqueConstraint("customer_id", "base_url", name="uq_competitors_customer_base_url"),
        sa.UniqueConstraint("customer_id", "name", name="uq_competitors_customer_name"),
    )
    op.create_index("ix_competitors_customer_id", "competitors", ["customer_id"])

    op.create_table(
        "products",
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("sku", sa.String(length=200), nullable=True),
        sa.Column("customer_product_url", sa.Text(), nullable=True),
        sa.Column("current_own_price", money, nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", uuid_type, nullable=False),
        sa.Column(
            "created_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))",
            name=op.f("ck_products_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "current_own_price IS NULL OR current_own_price >= 0",
            name=op.f("ck_products_own_price_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_products_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index("ix_products_customer_id", "products", ["customer_id"])
    op.create_index(
        "uq_products_customer_sku",
        "products",
        ["customer_id", "sku"],
        unique=True,
        sqlite_where=sa.text("sku IS NOT NULL"),
        postgresql_where=sa.text("sku IS NOT NULL"),
    )

    op.create_table(
        "competitor_products",
        sa.Column("product_id", uuid_type, nullable=False),
        sa.Column("competitor_id", uuid_type, nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("external_product_id", sa.String(length=300), nullable=True),
        sa.Column(
            "match_method",
            _enum("match_method", "manual", "identifier", "heuristic", "ai"),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("match_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("expected_name", sa.String(length=500), nullable=True),
        sa.Column("expected_currency", sa.String(length=3), nullable=True),
        sa.Column("minimum_valid_price", money, nullable=True),
        sa.Column("maximum_valid_price", money, nullable=True),
        sa.Column("schedule_interval_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "next_scrape_at",
            timestamp,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("current_price", money, nullable=True),
        sa.Column("current_currency", sa.String(length=3), nullable=True),
        sa.Column(
            "current_availability",
            _enum("availability", "in_stock", "out_of_stock", "preorder", "unknown"),
            nullable=True,
        ),
        sa.Column("current_observed_at", timestamp, nullable=True),
        sa.Column("last_attempt_at", timestamp, nullable=True),
        sa.Column("last_success_at", timestamp, nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", uuid_type, nullable=False),
        sa.Column(
            "created_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_competitor_products_consecutive_failures_nonnegative"),
        ),
        sa.CheckConstraint(
            "current_currency IS NULL OR "
            "(length(current_currency) = 3 AND current_currency = upper(current_currency))",
            name=op.f("ck_competitor_products_current_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "current_price IS NULL OR current_price >= 0",
            name=op.f("ck_competitor_products_current_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "expected_currency IS NULL OR "
            "(length(expected_currency) = 3 AND expected_currency = upper(expected_currency))",
            name=op.f("ck_competitor_products_expected_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name=op.f("ck_competitor_products_match_confidence_range"),
        ),
        sa.CheckConstraint(
            "maximum_valid_price IS NULL OR maximum_valid_price >= 0",
            name=op.f("ck_competitor_products_maximum_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "minimum_valid_price IS NULL OR minimum_valid_price >= 0",
            name=op.f("ck_competitor_products_minimum_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "minimum_valid_price IS NULL OR maximum_valid_price IS NULL "
            "OR minimum_valid_price <= maximum_valid_price",
            name=op.f("ck_competitor_products_valid_price_bounds_ordered"),
        ),
        sa.CheckConstraint(
            "schedule_interval_seconds IS NULL OR schedule_interval_seconds > 0",
            name=op.f("ck_competitor_products_schedule_interval_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_competitor_products_competitor_id_competitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_competitor_products_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competitor_products")),
        sa.UniqueConstraint("competitor_id", "product_url", name="uq_competitor_products_site_url"),
    )
    op.create_index(
        "ix_competitor_products_competitor_id", "competitor_products", ["competitor_id"]
    )
    op.create_index(
        "ix_competitor_products_due",
        "competitor_products",
        ["is_active", "next_scrape_at"],
    )
    op.create_index("ix_competitor_products_product_id", "competitor_products", ["product_id"])

    op.create_table(
        "scrape_results",
        sa.Column("run_key", sa.String(length=200), nullable=False),
        sa.Column("competitor_product_id", uuid_type, nullable=False),
        sa.Column(
            "status",
            _enum(
                "result_status",
                "queued",
                "running",
                "succeeded",
                "invalid",
                "failed",
                "timed_out",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column(
            "queued_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("started_at", timestamp, nullable=True),
        sa.Column("lease_token", uuid_type, nullable=True),
        sa.Column("lease_expires_at", timestamp, nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("observed_at", timestamp, nullable=True),
        sa.Column("finished_at", timestamp, nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("scraper_revision", sa.String(length=100), nullable=False),
        sa.Column("fetch_mode", _enum("fetch_mode", "http", "browser"), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("observed_name", sa.String(length=500), nullable=True),
        sa.Column("price", money, nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "availability",
            _enum("availability", "in_stock", "out_of_stock", "preorder", "unknown"),
            nullable=True,
        ),
        sa.Column("raw_price_text", sa.String(length=500), nullable=True),
        sa.Column("previous_price", money, nullable=True),
        sa.Column("previous_currency", sa.String(length=3), nullable=True),
        sa.Column("is_price_change", sa.Boolean(), nullable=True),
        sa.Column(
            "failure_kind",
            _enum(
                "failure_kind",
                "transport",
                "rate_limited",
                "access_denied",
                "not_found",
                "anti_bot",
                "extraction",
                "schema",
                "plausibility",
                "identity",
                "internal",
            ),
            nullable=True,
        ),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("extraction_evidence", sa.JSON(), nullable=False),
        sa.Column("html_artifact_uri", sa.Text(), nullable=True),
        sa.Column("html_sha256", sa.String(length=64), nullable=True),
        sa.Column("screenshot_uri", sa.Text(), nullable=True),
        sa.Column("id", uuid_type, nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_scrape_results_attempt_count_nonnegative")
        ),
        sa.CheckConstraint(
            "currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))",
            name=op.f("ck_scrape_results_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_scrape_results_duration_nonnegative"),
        ),
        sa.CheckConstraint(
            "html_sha256 IS NULL OR length(html_sha256) = 64",
            name=op.f("ck_scrape_results_html_sha256_length"),
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name=op.f("ck_scrape_results_http_status_range"),
        ),
        sa.CheckConstraint(
            "previous_currency IS NULL OR "
            "(length(previous_currency) = 3 AND previous_currency = upper(previous_currency))",
            name=op.f("ck_scrape_results_previous_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "previous_price IS NULL OR previous_price >= 0",
            name=op.f("ck_scrape_results_previous_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0",
            name=op.f("ck_scrape_results_price_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"],
            ["competitor_products.id"],
            name=op.f("fk_scrape_results_competitor_product_id_competitor_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scrape_results")),
        sa.UniqueConstraint("lease_token", name="uq_scrape_results_lease_token"),
        sa.UniqueConstraint("run_key", name="uq_scrape_results_run_key"),
    )
    op.create_index("ix_scrape_results_status_queued", "scrape_results", ["status", "queued_at"])
    op.create_index(
        "ix_scrape_results_target_queued",
        "scrape_results",
        ["competitor_product_id", "queued_at"],
    )
    op.create_index(
        "uq_scrape_results_one_active_per_target",
        "scrape_results",
        ["competitor_product_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "price_history",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("competitor_product_id", uuid_type, nullable=False),
        sa.Column("scrape_result_id", uuid_type, nullable=False),
        sa.Column("observed_at", timestamp, nullable=False),
        sa.Column("price", money, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "availability",
            _enum("availability", "in_stock", "out_of_stock", "preorder", "unknown"),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("previous_price", money, nullable=True),
        sa.Column("previous_currency", sa.String(length=3), nullable=True),
        sa.Column("change_amount", money, nullable=True),
        sa.Column("change_percent", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "change_kind",
            _enum(
                "change_kind",
                "initial",
                "unchanged",
                "increase",
                "decrease",
                "currency_changed",
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name=op.f("ck_price_history_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "previous_currency IS NULL OR "
            "(length(previous_currency) = 3 AND previous_currency = upper(previous_currency))",
            name=op.f("ck_price_history_previous_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "previous_price IS NULL OR previous_price >= 0",
            name=op.f("ck_price_history_previous_price_nonnegative"),
        ),
        sa.CheckConstraint("price >= 0", name=op.f("ck_price_history_price_nonnegative")),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"],
            ["competitor_products.id"],
            name=op.f("fk_price_history_competitor_product_id_competitor_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scrape_result_id"],
            ["scrape_results.id"],
            name=op.f("fk_price_history_scrape_result_id_scrape_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_history")),
        sa.UniqueConstraint("scrape_result_id", name="uq_price_history_scrape_result"),
    )
    op.create_index(
        "ix_price_history_target_observed",
        "price_history",
        ["competitor_product_id", "observed_at", "id"],
    )

    op.create_table(
        "repair_attempts",
        sa.Column("competitor_id", uuid_type, nullable=False),
        sa.Column("trigger_scrape_result_id", uuid_type, nullable=True),
        sa.Column(
            "status",
            _enum(
                "repair_status",
                "queued",
                "diagnosing",
                "candidate_ready",
                "testing",
                "validated",
                "rejected",
                "deployed",
                "failed",
                "rolled_back",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("failure_signature", sa.String(length=500), nullable=False),
        sa.Column("diagnostic_artifact_uri", sa.Text(), nullable=True),
        sa.Column("baseline_revision", sa.String(length=100), nullable=False),
        sa.Column("candidate_revision", sa.String(length=100), nullable=True),
        sa.Column("patch_uri", sa.Text(), nullable=True),
        sa.Column("patch_sha256", sa.String(length=64), nullable=True),
        sa.Column("lease_token", uuid_type, nullable=True),
        sa.Column("lease_expires_at", timestamp, nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("test_report", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("reviewer_decision", sa.String(length=100), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "queued_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("started_at", timestamp, nullable=True),
        sa.Column("candidate_ready_at", timestamp, nullable=True),
        sa.Column("testing_started_at", timestamp, nullable=True),
        sa.Column("validated_at", timestamp, nullable=True),
        sa.Column("deployed_at", timestamp, nullable=True),
        sa.Column("finished_at", timestamp, nullable=True),
        sa.Column("rolled_back_at", timestamp, nullable=True),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("id", uuid_type, nullable=False),
        sa.CheckConstraint(
            "patch_sha256 IS NULL OR length(patch_sha256) = 64",
            name=op.f("ck_repair_attempts_patch_sha256_length"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_repair_attempts_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status IN ('diagnosing', 'candidate_ready', 'testing') "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status NOT IN ('diagnosing', 'candidate_ready', 'testing') "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_repair_attempts_lease_matches_processing_status"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_repair_attempts_competitor_id_competitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_scrape_result_id"],
            ["scrape_results.id"],
            name=op.f("fk_repair_attempts_trigger_scrape_result_id_scrape_results"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repair_attempts")),
        sa.UniqueConstraint("lease_token", name="uq_repair_attempts_lease_token"),
    )
    op.create_index("ix_repair_attempts_status_queued", "repair_attempts", ["status", "queued_at"])
    op.create_index(
        "ix_repair_attempts_claimable",
        "repair_attempts",
        ["status", "lease_expires_at", "queued_at"],
    )
    op.create_index(
        "uq_repair_attempts_one_open_per_competitor",
        "repair_attempts",
        ["competitor_id"],
        unique=True,
        sqlite_where=sa.text(
            "status IN ('queued', 'diagnosing', 'candidate_ready', 'testing', 'validated')"
        ),
        postgresql_where=sa.text(
            "status IN ('queued', 'diagnosing', 'candidate_ready', 'testing', 'validated')"
        ),
    )

    op.create_table(
        "scraper_health",
        sa.Column("competitor_id", uuid_type, nullable=False),
        sa.Column(
            "status",
            _enum(
                "health_status",
                "healthy",
                "degraded",
                "broken",
                "repair_queued",
                "repairing",
                "disabled",
            ),
            server_default="healthy",
            nullable=False,
        ),
        sa.Column(
            "consecutive_repairable_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "recent_failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_attempt_at", timestamp, nullable=True),
        sa.Column("last_success_at", timestamp, nullable=True),
        sa.Column("last_failure_at", timestamp, nullable=True),
        sa.Column(
            "last_failure_kind",
            _enum(
                "failure_kind",
                "transport",
                "rate_limited",
                "access_denied",
                "not_found",
                "anti_bot",
                "extraction",
                "schema",
                "plausibility",
                "identity",
                "internal",
            ),
            nullable=True,
        ),
        sa.Column("last_failure_message", sa.Text(), nullable=True),
        sa.Column("last_scrape_result_id", uuid_type, nullable=True),
        sa.Column(
            "updated_at", timestamp, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "consecutive_repairable_failures >= 0",
            name=op.f("ck_scraper_health_repairable_failures_nonnegative"),
        ),
        sa.CheckConstraint(
            "recent_failure_count >= 0",
            name=op.f("ck_scraper_health_recent_failures_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_scraper_health_competitor_id_competitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_scrape_result_id"],
            ["scrape_results.id"],
            name=op.f("fk_scraper_health_last_scrape_result_id_scrape_results"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("competitor_id", name=op.f("pk_scraper_health")),
    )
    op.create_index("ix_scraper_health_status", "scraper_health", ["status"])


def downgrade() -> None:
    op.drop_index("ix_scraper_health_status", table_name="scraper_health")
    op.drop_table("scraper_health")
    op.drop_index("uq_repair_attempts_one_open_per_competitor", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_claimable", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_status_queued", table_name="repair_attempts")
    op.drop_table("repair_attempts")
    op.drop_index("ix_price_history_target_observed", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("uq_scrape_results_one_active_per_target", table_name="scrape_results")
    op.drop_index("ix_scrape_results_target_queued", table_name="scrape_results")
    op.drop_index("ix_scrape_results_status_queued", table_name="scrape_results")
    op.drop_table("scrape_results")
    op.drop_index("ix_competitor_products_product_id", table_name="competitor_products")
    op.drop_index("ix_competitor_products_due", table_name="competitor_products")
    op.drop_index("ix_competitor_products_competitor_id", table_name="competitor_products")
    op.drop_table("competitor_products")
    op.drop_index("uq_products_customer_sku", table_name="products")
    op.drop_index("ix_products_customer_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_competitors_customer_id", table_name="competitors")
    op.drop_table("competitors")
    op.drop_table("customers")

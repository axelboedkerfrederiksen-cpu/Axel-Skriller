from __future__ import annotations

import pytest
from pydantic import ValidationError

from price_monitor.config import Settings


def test_migration_database_url_defaults_to_runtime_database() -> None:
    settings = Settings(database_url="sqlite:///runtime.db")
    assert settings.effective_migration_database_url == "sqlite:///runtime.db"

    settings = Settings(
        database_url="postgresql+psycopg://app:password@pooler.example/monitor",
        migration_database_url="postgresql+psycopg://owner:password@db.example/monitor",
    )
    assert settings.effective_migration_database_url.endswith("@db.example/monitor")


def test_production_requires_postgres_and_api_token() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(environment="production", database_url="sqlite:///local.db")

    with pytest.raises(ValidationError, match="API_TOKEN"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db.example/monitor",
        )

    with pytest.raises(ValidationError, match="CRON_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db.example/monitor",
            api_token="a-secure-test-token-that-is-long-enough",
        )


def test_vercel_cron_secret_name_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    cron_secret = "a-secure-vercel-cron-secret-that-is-long-enough"
    monkeypatch.setenv("CRON_SECRET", cron_secret)

    settings = Settings()

    assert settings.cron_secret is not None
    assert settings.cron_secret.get_secret_value() == cron_secret


def test_vercel_cron_secret_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    vercel_secret = "the-vercel-cron-secret-that-is-long-enough"
    monkeypatch.setenv("CRON_SECRET", vercel_secret)
    monkeypatch.setenv(
        "PRICE_MONITOR_CRON_SECRET",
        "a-legacy-cron-secret-that-is-also-long-enough",
    )

    settings = Settings()

    assert settings.cron_secret is not None
    assert settings.cron_secret.get_secret_value() == vercel_secret


def test_ephemeral_demo_is_explicit_and_limited_to_tmp_sqlite() -> None:
    with pytest.raises(ValidationError, match="under /tmp"):
        Settings(ephemeral_demo=True, database_url="sqlite:///./var/demo.db")

    settings = Settings(
        environment="preview",
        ephemeral_demo=True,
        database_url="sqlite:////tmp/price-monitor-preview.db",
        api_token="a-secure-test-token-that-is-long-enough",
    )
    assert settings.ephemeral_demo is True


def test_ephemeral_demo_cannot_claim_to_be_production() -> None:
    with pytest.raises(ValidationError, match="cannot run in production"):
        Settings(
            environment="production",
            ephemeral_demo=True,
            database_url="postgresql+psycopg://user:password@db.example/monitor",
            api_token="a-secure-test-token-that-is-long-enough",
        )


def test_unknown_environment_cannot_bypass_production_guards() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        Settings(environment="prodution")  # type: ignore[arg-type]


def test_preview_requires_api_token() -> None:
    with pytest.raises(ValidationError, match="API_TOKEN"):
        Settings(
            environment="preview",
            ephemeral_demo=True,
            database_url="sqlite:////tmp/price-monitor-preview.db",
        )

from __future__ import annotations

import pytest
from pydantic import ValidationError

from price_monitor.config import Settings


def test_production_requires_postgres_and_api_token() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(environment="production", database_url="sqlite:///local.db")

    with pytest.raises(ValidationError, match="API_TOKEN"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db.example/monitor",
        )


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

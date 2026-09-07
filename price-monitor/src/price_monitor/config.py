from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PRICE_MONITOR_",
        extra="ignore",
    )

    environment: Literal["development", "test", "preview", "production"] = "development"
    database_url: str = "sqlite:///./var/price_monitor.db"
    artifact_root: Path = Path("./var/artifacts")
    adapter_runtime_root: Path = Path("./var/adapters")
    api_prefix: str = "/api/v1"
    api_token: SecretStr | None = Field(default=None, min_length=32)
    ephemeral_demo: bool = False

    user_agent: str = "PriceMonitorBeta/0.1 (+mailto:ops@example.invalid)"
    request_timeout_seconds: float = Field(default=15.0, ge=1, le=120)
    maximum_response_bytes: int = Field(default=2_000_000, ge=10_000, le=20_000_000)
    default_minimum_request_interval_ms: int = Field(default=1_000, ge=0)
    maximum_retries: int = Field(default=2, ge=0, le=5)
    respect_robots_txt: bool = True

    repair_failure_threshold: int = Field(default=3, ge=1, le=20)
    repair_minimum_distinct_targets: int = Field(default=2, ge=1, le=20)
    repair_cooldown_seconds: int = Field(default=3_600, ge=0)
    repair_runner_image: str | None = None
    repair_provider: Literal["deterministic", "disabled", "openai"] = "deterministic"
    openai_repair_model: str | None = Field(default=None, min_length=1, max_length=200)
    openai_api_key: SecretStr | None = None
    scheduler_poll_seconds: float = Field(default=5.0, ge=0.2, le=300)
    worker_lease_seconds: int = Field(default=300, ge=30, le=3_600)

    @model_validator(mode="after")
    def production_requires_postgres(self) -> Settings:
        if self.environment == "production" and not self.database_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("production requires a PostgreSQL database URL")
        if self.environment in {"preview", "production"} and self.api_token is None:
            raise ValueError("hosted environments require PRICE_MONITOR_API_TOKEN")
        if self.ephemeral_demo:
            if self.environment == "production":
                raise ValueError("ephemeral demo storage cannot run in production mode")
            if not self.database_url.startswith("sqlite") or "/tmp/" not in self.database_url:
                raise ValueError("ephemeral demo storage must use a SQLite database under /tmp")
        if self.repair_provider == "openai" and (
            self.openai_repair_model is None or self.openai_api_key is None
        ):
            raise ValueError(
                "OpenAI repair requires PRICE_MONITOR_OPENAI_REPAIR_MODEL and "
                "PRICE_MONITOR_OPENAI_API_KEY"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

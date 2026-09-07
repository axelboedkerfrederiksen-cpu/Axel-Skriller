from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from typer.testing import CliRunner

from price_monitor.cli import app
from price_monitor.config import get_settings

pytestmark = pytest.mark.integration


def test_init_db_resolves_migrations_from_runtime_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = Path(__file__).resolve().parents[2]
    shutil.copy2(source_root / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(source_root / "migrations", tmp_path / "migrations")
    database_path = tmp_path / "installed-package.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "PRICE_MONITOR_DATABASE_URL",
        f"sqlite:///{database_path}",
    )
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["init-db"])
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0, result.output
    assert "Database is at the latest migration" in result.output
    database_engine = create_engine(f"sqlite:///{database_path}")
    try:
        assert "scrape_results" in inspect(database_engine).get_table_names()
    finally:
        database_engine.dispose()

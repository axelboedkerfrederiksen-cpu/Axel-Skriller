from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import typer
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine

from price_monitor.config import Settings, get_settings
from price_monitor.db import (
    SessionFactory,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from price_monitor.demo import run_demo
from price_monitor.domain.enums import FetchMode
from price_monitor.domain.types import ScrapeTarget
from price_monitor.fetchers import HttpFetcher, RobotsTxtPolicy
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.queue import ScrapeQueue
from price_monitor.services.repair_coordinator import RepairCoordinator
from price_monitor.services.validation import ProductValidator
from price_monitor.services.worker import ScrapeWorker

app = typer.Typer(
    no_args_is_help=True,
    help="Operate the competitor price-monitoring beta.",
)


def _runtime() -> tuple[Settings, Engine, SessionFactory, AdapterRegistry]:
    settings = get_settings()
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    settings.adapter_runtime_root.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    registry = AdapterRegistry(settings.adapter_runtime_root)
    return settings, engine, factory, registry


@app.command("init-db")
def init_db() -> None:
    """Apply all database migrations."""

    settings = get_settings()
    migration_database_url = settings.effective_migration_database_url
    if migration_database_url.startswith("sqlite"):
        Path("var").mkdir(parents=True, exist_ok=True)
    config_path = Path(os.getenv("PRICE_MONITOR_ALEMBIC_CONFIG", "alembic.ini")).resolve()
    if not config_path.is_file():
        raise typer.BadParameter(
            "Alembic configuration was not found; run from the deployment root or set "
            "PRICE_MONITOR_ALEMBIC_CONFIG"
        )
    config = AlembicConfig(config_path)
    config.set_main_option("sqlalchemy.url", migration_database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    typer.echo("Database is at the latest migration.")


@app.command("schedule-once")
def schedule_once(
    limit: Annotated[int, typer.Option(min=1, max=10_000)] = 100,
) -> None:
    """Queue currently due targets once."""

    _, engine, factory, _ = _runtime()
    try:
        with session_scope(factory) as session:
            queued = ScrapeQueue().enqueue_due(session, limit=limit)
        typer.echo(json.dumps({"queued": len(queued)}))
    finally:
        engine.dispose()


@app.command("scheduler")
def scheduler() -> None:
    """Continuously queue due monitoring targets."""

    settings, engine, factory, _ = _runtime()
    queue = ScrapeQueue(lease_seconds=settings.worker_lease_seconds)
    try:
        while True:
            with session_scope(factory) as session:
                queued = queue.enqueue_due(session)
            if queued:
                logging.info("queued %d due scrape(s)", len(queued))
            time.sleep(settings.scheduler_poll_seconds)
    except KeyboardInterrupt:
        typer.echo("Scheduler stopped.")
    finally:
        engine.dispose()


@app.command("worker-once")
def worker_once() -> None:
    """Process at most one queued scrape."""

    asyncio.run(_worker_loop(once=True))


@app.command("worker")
def worker() -> None:
    """Continuously process queued scrapes."""

    try:
        asyncio.run(_worker_loop(once=False))
    except KeyboardInterrupt:
        typer.echo("Worker stopped.")


async def _worker_loop(*, once: bool) -> None:
    settings, engine, factory, registry = _runtime()
    scrape_worker = ScrapeWorker(
        session_factory=factory,
        settings=settings,
        registry=registry,
    )
    try:
        while True:
            processed = await scrape_worker.process_one()
            if once:
                typer.echo(json.dumps({"processed": processed}))
                return
            if not processed:
                await asyncio.sleep(settings.scheduler_poll_seconds)
    finally:
        await scrape_worker.aclose()
        engine.dispose()


@app.command("repair-once")
def repair_once() -> None:
    """Evaluate and stage at most one repair; never deploy it automatically."""

    settings, engine, factory, registry = _runtime()
    try:
        coordinator = RepairCoordinator(
            session_factory=factory,
            settings=settings,
            registry=registry,
        )
        result = coordinator.evaluate_one()
        typer.echo(json.dumps(asdict(result) if result else {"processed": False}, default=str))
    finally:
        engine.dispose()


@app.command("repair-worker")
def repair_worker() -> None:
    """Continuously evaluate repairs, leaving validated candidates undeployed."""

    settings, engine, factory, registry = _runtime()
    coordinator = RepairCoordinator(
        session_factory=factory,
        settings=settings,
        registry=registry,
    )
    try:
        while True:
            result = coordinator.evaluate_one()
            if result:
                logging.info("repair %s became %s", result.repair_id, result.status)
            else:
                time.sleep(settings.scheduler_poll_seconds)
    except KeyboardInterrupt:
        typer.echo("Repair worker stopped.")
    finally:
        engine.dispose()


@app.command("deploy-repair")
def deploy_repair(repair_id: UUID) -> None:
    """Explicitly deploy one deterministically validated repair."""

    settings, engine, factory, registry = _runtime()
    try:
        result = RepairCoordinator(
            session_factory=factory,
            settings=settings,
            registry=registry,
        ).deploy(repair_id)
        typer.echo(json.dumps(asdict(result), default=str))
    finally:
        engine.dispose()


@app.command("rollback")
def rollback(competitor_id: UUID) -> None:
    """Atomically point a competitor back to its previous scraper revision."""

    settings, engine, factory, registry = _runtime()
    try:
        revision = RepairCoordinator(
            session_factory=factory,
            settings=settings,
            registry=registry,
        ).rollback_competitor(competitor_id)
        typer.echo(json.dumps({"active_revision": revision}))
    finally:
        engine.dispose()


@app.command("demo")
def demo(
    work_directory: Annotated[
        Path | None,
        typer.Option(help="Keep demo artifacts in this directory instead of a temporary one."),
    ] = None,
) -> None:
    """Run the offline scrape → change → break → repair → reject demonstration."""

    if work_directory is not None:
        report = asyncio.run(run_demo(work_directory))
        typer.echo(json.dumps(asdict(report), indent=2))
        return
    with tempfile.TemporaryDirectory(prefix="price-monitor-demo-") as directory:
        report = asyncio.run(run_demo(Path(directory)))
        typer.echo(json.dumps(asdict(report), indent=2))


@app.command("live-smoke")
def live_smoke(
    url: Annotated[
        str,
        typer.Option(help="Public Books to Scrape product URL to inspect."),
    ] = ("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"),
) -> None:
    """Opt in to one respectful live fetch from the public scraping sandbox."""

    asyncio.run(_live_smoke(url))


async def _live_smoke(url: str) -> None:
    settings = get_settings()
    registry = AdapterRegistry(settings.adapter_runtime_root)
    spec = registry.active_spec("books_to_scrape")
    host = urlsplit(url).hostname or ""
    if host.lower().rstrip(".") not in spec.allowed_hosts:
        raise typer.BadParameter("URL must use the Books to Scrape adapter hostname")
    target = ScrapeTarget(
        competitor_product_id="live-smoke",
        url=url,
        allowed_hosts=spec.allowed_hosts,
        adapter_key=spec.key,
        adapter_revision=spec.revision,
        fetch_mode=FetchMode.HTTP,
        expected_currency="GBP",
        minimum_valid_price=Decimal("0.01"),
        maximum_valid_price=Decimal("1000000"),
    )
    async with HttpFetcher.from_settings(settings) as fetcher:
        if settings.respect_robots_txt:
            await RobotsTxtPolicy(user_agent=settings.user_agent).enforce(
                fetcher=fetcher,
                url=url,
                allowed_hosts=spec.allowed_hosts,
            )
        page = await fetcher.fetch(url, allowed_hosts=spec.allowed_hosts)
    product = registry.scraper_at(spec.key, spec.revision).extract(page)
    validation = ProductValidator().validate(product, target)
    typer.echo(
        json.dumps(
            {
                "accepted": validation.accepted,
                "name": product.name,
                "price": str(product.price),
                "currency": product.currency,
                "availability": product.availability.value,
                "url": str(product.product_url),
                "issues": [issue.model_dump(mode="json") for issue in validation.issues],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()

"""Typed persistence models and session helpers."""

from price_monitor.db.alert_models import AlertRule
from price_monitor.db.base import Base
from price_monitor.db.models import (
    ALL_MODELS,
    Competitor,
    CompetitorProduct,
    Customer,
    PriceHistory,
    Product,
    RepairAttempt,
    ScrapeResult,
    ScraperHealth,
)
from price_monitor.db.session import (
    SessionFactory,
    SessionLocal,
    create_db_engine,
    create_schema,
    create_session_factory,
    drop_schema,
    engine,
    get_db_session,
    get_session,
    normalize_database_url,
    session_scope,
)

__all__ = [
    "ALL_MODELS",
    "AlertRule",
    "Base",
    "Competitor",
    "CompetitorProduct",
    "Customer",
    "PriceHistory",
    "Product",
    "RepairAttempt",
    "ScrapeResult",
    "ScraperHealth",
    "SessionFactory",
    "SessionLocal",
    "create_db_engine",
    "create_schema",
    "create_session_factory",
    "drop_schema",
    "engine",
    "get_db_session",
    "get_session",
    "normalize_database_url",
    "session_scope",
]

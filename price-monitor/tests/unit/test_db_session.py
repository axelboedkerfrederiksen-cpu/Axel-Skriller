from sqlalchemy.pool import NullPool

from price_monitor.db import create_db_engine


def test_transaction_pooler_uses_serverless_safe_engine_options() -> None:
    engine = create_db_engine(
        "postgresql+psycopg://user:password@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
    )
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()

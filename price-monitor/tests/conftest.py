from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.db import create_db_engine, create_schema, create_session_factory


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()

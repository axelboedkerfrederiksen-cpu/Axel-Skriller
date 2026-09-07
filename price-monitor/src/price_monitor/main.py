from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from price_monitor.api.dependencies import SessionDep, require_api_token
from price_monitor.api.router import router
from price_monitor.config import Settings, get_settings
from price_monitor.db import create_db_engine, create_schema, create_session_factory
from price_monitor.db.models import Customer
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    ServiceError,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    runtime_engine = create_db_engine(runtime_settings.database_url)
    runtime_session_factory = create_session_factory(runtime_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        runtime_settings.artifact_root.mkdir(parents=True, exist_ok=True)
        runtime_settings.adapter_runtime_root.mkdir(parents=True, exist_ok=True)
        if runtime_settings.ephemeral_demo:
            create_schema(runtime_engine)
        try:
            yield
        finally:
            runtime_engine.dispose()

    app = FastAPI(
        title="Price Monitor API",
        version="0.1.0",
        description=(
            "Deterministic competitor price monitoring with guarded scraper repair. "
            "Hosted API access requires the configured bearer token."
        ),
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.db_engine = runtime_engine
    app.state.session_factory = runtime_session_factory
    app.state.adapter_registry = AdapterRegistry(runtime_settings.adapter_runtime_root)
    app.include_router(
        router,
        prefix=runtime_settings.api_prefix,
        dependencies=[Depends(require_api_token)],
    )

    @app.get("/healthz", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def ready(session: SessionDep) -> dict[str, str]:
        session.execute(select(Customer.id).limit(1))
        return {"status": "ready"}

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        if isinstance(exc, NotFoundError):
            status_code = 404
        elif isinstance(exc, ConflictError):
            status_code = 409
        elif isinstance(exc, InvalidRequestError):
            status_code = 422
        else:
            status_code = 400
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return app


app = create_app()

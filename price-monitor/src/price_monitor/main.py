from __future__ import annotations

import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import select

from price_monitor.api.cron_router import router as cron_router
from price_monitor.api.dependencies import SessionDep, require_api_token
from price_monitor.api.docs import (
    SWAGGER_OAUTH2_REDIRECT_URL,
    api_docs_response,
    oauth2_redirect_response,
)
from price_monitor.api.home import homepage_response
from price_monitor.api.router import router
from price_monitor.api.ui_auth import (
    UI_REQUEST_HEADER,
    UiSessionRead,
    clear_ui_session_cookie,
    request_has_ui_session,
    set_ui_session_cookie,
)
from price_monitor.config import Settings, get_settings
from price_monitor.db import create_db_engine, create_schema, create_session_factory
from price_monitor.db.models import Customer
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.development_seed import seed_development_workspace
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
        if runtime_settings.seed_development_data:
            await seed_development_workspace(
                settings=runtime_settings,
                session_factory=runtime_session_factory,
                registry=app.state.adapter_registry,
            )
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
        docs_url=None,
        redoc_url="/redoc",
        lifespan=lifespan,
        swagger_ui_oauth2_redirect_url=SWAGGER_OAUTH2_REDIRECT_URL,
    )
    app.state.settings = runtime_settings
    app.state.db_engine = runtime_engine
    app.state.session_factory = runtime_session_factory
    app.state.adapter_registry = AdapterRegistry(runtime_settings.adapter_runtime_root)
    web_root = Path(__file__).resolve().parent / "web"
    api_router = APIRouter()
    api_router.include_router(router)
    app.include_router(
        api_router,
        prefix=runtime_settings.api_prefix,
        dependencies=[Depends(require_api_token)],
    )
    app.include_router(cron_router)

    @app.get("/", include_in_schema=False)
    def home() -> HTMLResponse:
        return homepage_response()

    @app.get("/static/price-monitor/app.css", include_in_schema=False)
    def workspace_styles() -> FileResponse:
        return FileResponse(
            web_root / "app.css",
            media_type="text/css",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/static/price-monitor/app.js", include_in_schema=False)
    def workspace_script() -> FileResponse:
        return FileResponse(
            web_root / "app.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/products", include_in_schema=False)
    def products_page() -> HTMLResponse:
        return homepage_response()

    @app.get("/products/new", include_in_schema=False)
    def new_product() -> HTMLResponse:
        return homepage_response()

    @app.get("/products/{product_id}", include_in_schema=False)
    def product_page(product_id: str) -> HTMLResponse:
        del product_id
        return homepage_response()

    @app.get("/competitors", include_in_schema=False)
    def competitors_page() -> HTMLResponse:
        return homepage_response()

    @app.get("/alerts", include_in_schema=False)
    def alerts_page() -> HTMLResponse:
        return homepage_response()

    @app.get("/session", response_model=UiSessionRead, include_in_schema=False)
    def session_status(request: Request, response: Response) -> UiSessionRead:
        response.headers["Cache-Control"] = "no-store"
        protected = runtime_settings.api_token is not None
        return UiSessionRead(
            authenticated=not protected or request_has_ui_session(request),
            protected=protected,
        )

    @app.post("/session", response_model=UiSessionRead, include_in_schema=False)
    async def login(request: Request) -> JSONResponse:
        if request.headers.get(UI_REQUEST_HEADER) != "1":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="UI request confirmation required",
            )
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if content_length > 8_192:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="access key request is invalid",
            )
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8_192:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="access key request is invalid",
                )
            body.extend(chunk)
        try:
            decoded = json.loads(body)
            supplied = decoded.get("access_key") if isinstance(decoded, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            supplied = None
        if not isinstance(supplied, str) or not 1 <= len(supplied) <= 4_096:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="access key request is invalid",
            )
        configured = runtime_settings.api_token
        if configured is not None and not hmac.compare_digest(
            supplied.encode("utf-8"),
            configured.get_secret_value().encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="access key not accepted",
            )
        response = JSONResponse(
            {"authenticated": True, "protected": configured is not None},
            headers={"Cache-Control": "no-store"},
        )
        if configured is not None:
            set_ui_session_cookie(response, runtime_settings)
        return response

    @app.delete("/session", response_model=UiSessionRead, include_in_schema=False)
    def logout(request: Request) -> JSONResponse:
        if request.headers.get(UI_REQUEST_HEADER) != "1":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="UI request confirmation required",
            )
        response = JSONResponse(
            {
                "authenticated": runtime_settings.api_token is None,
                "protected": runtime_settings.api_token is not None,
            },
            headers={"Cache-Control": "no-store"},
        )
        clear_ui_session_cookie(response, runtime_settings)
        return response

    @app.get("/docs", include_in_schema=False)
    def api_docs() -> HTMLResponse:
        return api_docs_response(openapi_url=app.openapi_url or "/openapi.json")

    @app.get(SWAGGER_OAUTH2_REDIRECT_URL, include_in_schema=False)
    def swagger_ui_redirect() -> HTMLResponse:
        return oauth2_redirect_response()

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

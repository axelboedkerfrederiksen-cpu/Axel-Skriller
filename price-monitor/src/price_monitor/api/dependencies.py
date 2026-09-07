import hmac
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from price_monitor.db.session import get_db_session
from price_monitor.services.adapter_registry import AdapterRegistry

_bearer = HTTPBearer(auto_error=False)


def get_adapter_registry(request: Request) -> AdapterRegistry:
    return cast(AdapterRegistry, request.app.state.adapter_registry)


def require_api_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Require one deployment token when configured; local development stays open."""

    configured = request.app.state.settings.api_token
    if configured is None:
        return
    supplied = credentials.credentials if credentials and credentials.scheme == "Bearer" else ""
    if not hmac.compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )


SessionDep = Annotated[Session, Depends(get_db_session)]
AdapterRegistryDep = Annotated[AdapterRegistry, Depends(get_adapter_registry)]

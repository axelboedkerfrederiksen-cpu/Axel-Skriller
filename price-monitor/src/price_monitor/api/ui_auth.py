from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Final

from fastapi import HTTPException, Request, Response, status
from pydantic import BaseModel

from price_monitor.config import Settings

UI_SESSION_COOKIE: Final = "pm_ui_session"
UI_REQUEST_HEADER: Final = "X-Price-Monitor-UI"
_SESSION_VERSION: Final = "v1"
_SESSION_LIFETIME_SECONDS: Final = 12 * 60 * 60
_SESSION_CONTEXT: Final = b"price-monitor-ui-session-v1"


class UiSessionRead(BaseModel):
    authenticated: bool
    protected: bool


def _configured_secret(settings: Settings) -> bytes | None:
    if settings.api_token is None:
        return None
    return settings.api_token.get_secret_value().encode("utf-8")


def _signature(secret: bytes, payload: str) -> str:
    digest = hmac.new(secret, _SESSION_CONTEXT + payload.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_ui_session(settings: Settings) -> str:
    secret = _configured_secret(settings)
    if secret is None:
        raise RuntimeError("a UI session is unnecessary without a configured API token")
    payload = f"{_SESSION_VERSION}.{int(time.time())}.{secrets.token_urlsafe(18)}"
    return f"{payload}.{_signature(secret, payload)}"


def validate_ui_session(value: str | None, settings: Settings) -> bool:
    secret = _configured_secret(settings)
    if secret is None:
        return True
    if not value or len(value) > 256:
        return False
    try:
        version, issued_text, nonce, supplied_signature = value.split(".", maxsplit=3)
        if not re.fullmatch(r"[0-9]{1,12}", issued_text):
            return False
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", nonce):
            return False
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", supplied_signature):
            return False
        issued_at = int(issued_text)
    except (TypeError, ValueError):
        return False
    if version != _SESSION_VERSION or not nonce:
        return False
    now = int(time.time())
    if issued_at > now + 60 or now - issued_at > _SESSION_LIFETIME_SECONDS:
        return False
    payload = f"{version}.{issued_text}.{nonce}"
    expected_signature = _signature(secret, payload)
    return hmac.compare_digest(
        supplied_signature.encode("ascii"),
        expected_signature.encode("ascii"),
    )


def request_has_ui_session(request: Request) -> bool:
    return validate_ui_session(
        request.cookies.get(UI_SESSION_COOKIE),
        request.app.state.settings,
    )


def require_same_origin_ui_mutation(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get(UI_REQUEST_HEADER) != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="UI request confirmation required",
        )


def set_ui_session_cookie(response: Response, settings: Settings) -> None:
    response.set_cookie(
        key=UI_SESSION_COOKIE,
        value=issue_ui_session(settings),
        max_age=_SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=settings.environment in {"preview", "production"},
        samesite="strict",
        path="/",
    )


def clear_ui_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=UI_SESSION_COOKIE,
        httponly=True,
        secure=settings.environment in {"preview", "production"},
        samesite="strict",
        path="/",
    )


__all__ = [
    "UI_REQUEST_HEADER",
    "UI_SESSION_COOKIE",
    "UiSessionRead",
    "clear_ui_session_cookie",
    "request_has_ui_session",
    "require_same_origin_ui_mutation",
    "set_ui_session_cookie",
    "validate_ui_session",
]

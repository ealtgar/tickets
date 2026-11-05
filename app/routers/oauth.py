import os
import secrets
import urllib.parse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..oauth import (
    OAuthError,
    build_authorization_url,
    configured_providers,
    exchange_code,
    fetch_profile,
    get_provider,
)
from ..security import REFRESH_COOKIE_SECURE
from .auth import issue_tokens, set_refresh_cookie

router = APIRouter(prefix="/api/auth/oauth", tags=["auth"])

STATE_COOKIE_NAME = "oauth_state"
STATE_COOKIE_PATH = "/api/auth/oauth"
STATE_TTL_SECONDS = 600

FRONTEND_REDIRECT = os.getenv("OAUTH_FRONTEND_REDIRECT", "/")


def _callback_base(request: Request) -> str:
    return os.getenv("OAUTH_CALLBACK_BASE_URL") or str(request.base_url)


def _redirect_uri(request: Request, provider: str) -> str:
    base = _callback_base(request).rstrip("/")
    return f"{base}/api/auth/oauth/{provider}/callback"


def _with_query(url: str, **params: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update(params)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urllib.parse.urlencode(query),
            parts.fragment,
        )
    )


def _error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse(
        _with_query(FRONTEND_REDIRECT, oauth_error=message),
        status_code=302,
    )


def _set_state_cookie(response: RedirectResponse, state: str) -> None:
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite="lax",
        path=STATE_COOKIE_PATH,
    )


def _clear_state_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(
        key=STATE_COOKIE_NAME,
        path=STATE_COOKIE_PATH,
        secure=REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


@router.get("/providers")
def list_providers():
    return {"providers": configured_providers()}


@router.get("/{provider}/login")
def oauth_login(provider: str, request: Request):
    try:
        config = get_provider(provider)
    except OAuthError as exc:
        return _error_redirect(str(exc))

    state = secrets.token_urlsafe(32)
    authorization_url = build_authorization_url(
        config, _redirect_uri(request, config.name), state
    )
    response = RedirectResponse(authorization_url, status_code=302)
    _set_state_cookie(response, state)
    return response


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    if error:
        return _error_redirect("La autorización fue cancelada o rechazada")

    try:
        config = get_provider(provider)
    except OAuthError as exc:
        return _error_redirect(str(exc))

    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    if (
        not state
        or not cookie_state
        or not secrets.compare_digest(state, cookie_state)
    ):
        return _error_redirect("Estado OAuth inválido o expirado")

    if not code:
        return _error_redirect("Falta el código de autorización")

    try:
        access_token = exchange_code(
            config, code, _redirect_uri(request, config.name)
        )
        profile = fetch_profile(config, access_token)
    except OAuthError as exc:
        return _error_redirect(str(exc))

    user = crud.get_or_create_oauth_user(db, profile)
    if not user.is_active:
        return _error_redirect("El usuario está inactivo")

    tokens = issue_tokens(db, user, request)
    response = RedirectResponse(
        _with_query(FRONTEND_REDIRECT, oauth="success"), status_code=302
    )
    set_refresh_cookie(response, tokens.refresh_token)
    _clear_state_cookie(response)
    return response

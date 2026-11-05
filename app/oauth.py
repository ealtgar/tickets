"""Flujo OAuth2 (authorization code) para GitHub y Google.

Solo usa la librería estándar (``urllib``) para no añadir dependencias.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable

HTTP_TIMEOUT_SECONDS = float(os.getenv("OAUTH_HTTP_TIMEOUT_SECONDS", "10"))
USER_AGENT = "tickets-app"


class OAuthError(Exception):
    """Error controlado durante el flujo OAuth (mensaje apto para el usuario)."""


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    email_url: str | None = None


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_user_id: str
    email: str | None
    email_verified: bool
    username: str | None
    display_name: str | None


@dataclass(frozen=True)
class _ProviderDefinition:
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    email_url: str | None = None


_DEFINITIONS: dict[str, _ProviderDefinition] = {
    "github": _ProviderDefinition(
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scope="read:user user:email",
        email_url="https://api.github.com/user/emails",
    ),
    "google": _ProviderDefinition(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
    ),
}


def _env_name(provider: str, suffix: str) -> str:
    return f"{provider.upper()}_{suffix}"


def get_provider(name: str) -> OAuthProvider:
    """Devuelve la configuración del proveedor o lanza ``OAuthError``."""
    provider = (name or "").lower()
    definition = _DEFINITIONS.get(provider)
    if definition is None:
        raise OAuthError("Proveedor de autenticación no soportado")

    client_id = os.getenv(_env_name(provider, "CLIENT_ID"))
    client_secret = os.getenv(_env_name(provider, "CLIENT_SECRET"))
    if not client_id or not client_secret:
        raise OAuthError("Proveedor de autenticación no configurado")

    return OAuthProvider(
        name=provider,
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=definition.authorize_url,
        token_url=definition.token_url,
        userinfo_url=definition.userinfo_url,
        scope=definition.scope,
        email_url=definition.email_url,
    )


def configured_providers() -> list[str]:
    providers = []
    for name in _DEFINITIONS:
        if os.getenv(_env_name(name, "CLIENT_ID")) and os.getenv(
            _env_name(name, "CLIENT_SECRET")
        ):
            providers.append(name)
    return providers


def build_authorization_url(
    provider: OAuthProvider, redirect_uri: str, state: str
) -> str:
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
    }
    if provider.name == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    separator = "&" if "?" in provider.authorize_url else "?"
    return f"{provider.authorize_url}{separator}{urllib.parse.urlencode(params)}"


def _request_json(
    request: urllib.request.Request, error_message: str
) -> dict | list:
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError(error_message) from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthError(error_message) from exc


def exchange_code(provider: OAuthProvider, code: str, redirect_uri: str) -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        provider.token_url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    payload = _request_json(
        request, "No se pudo canjear el código de autorización"
    )
    if not isinstance(payload, dict):
        raise OAuthError("Respuesta inválida del proveedor")
    if payload.get("error"):
        description = payload.get("error_description") or payload["error"]
        raise OAuthError(f"El proveedor rechazó la autorización: {description}")
    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthError("El proveedor no devolvió un token de acceso")
    return str(access_token)


def _get_json(url: str, access_token: str, error_message: str) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
    )
    return _request_json(request, error_message)


def _github_email(provider: OAuthProvider, access_token: str) -> tuple[str | None, bool]:
    if not provider.email_url:
        return None, False
    try:
        emails = _get_json(
            provider.email_url,
            access_token,
            "No se pudieron obtener los correos de GitHub",
        )
    except OAuthError:
        return None, False
    if not isinstance(emails, list):
        return None, False

    primary_verified = None
    first_verified = None
    for entry in emails:
        if not isinstance(entry, dict) or not entry.get("email"):
            continue
        if not entry.get("verified"):
            continue
        if first_verified is None:
            first_verified = entry["email"]
        if entry.get("primary"):
            primary_verified = entry["email"]
            break
    email = primary_verified or first_verified
    return email, email is not None


def fetch_profile(provider: OAuthProvider, access_token: str) -> OAuthProfile:
    if provider.name == "github":
        data = _get_json(
            provider.userinfo_url, access_token, "No se pudo leer el perfil de GitHub"
        )
        if not isinstance(data, dict) or data.get("id") is None:
            raise OAuthError("Respuesta inválida del perfil de GitHub")
        email = data.get("email")
        verified = False
        if not email:
            email, verified = _github_email(provider, access_token)
        return OAuthProfile(
            provider=provider.name,
            provider_user_id=str(data["id"]),
            email=email,
            email_verified=verified,
            username=data.get("login") or data.get("name"),
            display_name=data.get("name"),
        )

    if provider.name == "google":
        data = _get_json(
            provider.userinfo_url, access_token, "No se pudo leer el perfil de Google"
        )
        if not isinstance(data, dict) or data.get("sub") is None:
            raise OAuthError("Respuesta inválida del perfil de Google")
        email = data.get("email")
        return OAuthProfile(
            provider=provider.name,
            provider_user_id=str(data["sub"]),
            email=email,
            email_verified=bool(data.get("email_verified")),
            username=(email.split("@")[0] if email else data.get("name")),
            display_name=data.get("name"),
        )

    raise OAuthError("Proveedor de autenticación no soportado")


def iter_providers() -> Iterable[str]:
    return _DEFINITIONS.keys()

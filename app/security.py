import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
REFRESH_SECRET_KEY = os.getenv("REFRESH_SECRET_KEY") or SECRET_KEY
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
JWT_ISSUER = os.getenv("JWT_ISSUER", "tickets-api")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "tickets-web")
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "5"))

REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "tickets_refresh_token")
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/api/auth")
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
}
_SAMESITE_VALUES = ("lax", "strict", "none")
REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = (
    os.getenv("REFRESH_COOKIE_SAMESITE", "lax").lower()
    if os.getenv("REFRESH_COOKIE_SAMESITE", "lax").lower() in _SAMESITE_VALUES
    else "lax"
)

BCRYPT_MAX_BYTES = 72

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

# Razones de revocación de un refresh token.
REVOKE_ROTATED = "rotated"
REVOKE_LOGOUT = "logout"
REVOKE_REUSE = "reuse"
REVOKE_EXPIRED = "expired"
REVOKE_LOGOUT_ALL = "logout_all"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def access_token_expiry(expires_minutes: int | None = None) -> datetime:
    return utcnow() + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )


def refresh_token_expiry(expires_days: int | None = None) -> datetime:
    return utcnow() + timedelta(days=expires_days or REFRESH_TOKEN_EXPIRE_DAYS)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "iat": now,
        "exp": access_token_expiry(expires_minutes),
        "type": ACCESS_TOKEN_TYPE,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    subject: str,
    expires_days: int | None = None,
    *,
    jti: str | None = None,
    family_id: str | None = None,
    expires_at: datetime | None = None,
) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at or refresh_token_expiry(expires_days),
        "type": REFRESH_TOKEN_TYPE,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": jti or str(uuid.uuid4()),
    }
    if family_id:
        payload["fam"] = family_id
    return jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str, secret: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            leeway=JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "type", "jti"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def decode_access_token(token: str) -> dict | None:
    return _decode(token, SECRET_KEY, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict | None:
    return _decode(token, REFRESH_SECRET_KEY, REFRESH_TOKEN_TYPE)

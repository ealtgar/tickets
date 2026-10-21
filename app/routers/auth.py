import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    REVOKE_EXPIRED,
    REVOKE_LOGOUT,
    REVOKE_LOGOUT_ALL,
    REVOKE_REUSE,
    REVOKE_ROTATED,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    refresh_token_expiry,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

REUSE_DETAIL = (
    "Se ha detectado la reutilización de un refresh token. "
    "Se han revocado todas las sesiones de ese usuario."
)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _client_info(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None
    return (
        user_agent[:255] if user_agent else None,
        client_ip[:45] if client_ip else None,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=REFRESH_COOKIE_SAMESITE,
    )


def _candidate_tokens(
    request: Request, payload: schemas.RefreshRequest | None
) -> list[str]:
    """La cookie httpOnly manda; el cuerpo JSON es el plan B para clientes
    que no gestionen cookies."""
    tokens = []
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie_token:
        tokens.append(cookie_token)
    if payload and payload.refresh_token:
        tokens.append(payload.refresh_token)
    return list(dict.fromkeys(tokens))


def _issue_tokens(
    db: Session,
    user: models.User,
    request: Request | None = None,
    *,
    family_id: str | None = None,
    rotate_from: models.RefreshToken | None = None,
) -> schemas.Token:
    """Emite un access token nuevo y rota el refresh token."""
    jti = str(uuid.uuid4())
    family_id = family_id or str(uuid.uuid4())
    expires_at = refresh_token_expiry()
    refresh_token = create_refresh_token(
        user.username,
        jti=jti,
        family_id=family_id,
        expires_at=expires_at,
    )
    user_agent, client_ip = _client_info(request)
    crud.create_refresh_token(
        db,
        user=user,
        jti=jti,
        family_id=family_id,
        expires_at=expires_at,
        user_agent=user_agent,
        client_ip=client_ip,
    )
    if rotate_from is not None:
        crud.revoke_refresh_token(
            db, rotate_from, REVOKE_ROTATED, replaced_by_jti=jti
        )
    return schemas.Token(
        access_token=create_access_token(user.username),
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _resolve_refresh_record(
    db: Session, candidates: list[str]
) -> tuple[models.RefreshToken | None, dict | None]:
    """Valida los refresh tokens candidatos y devuelve el registro vivo.

    Si algún token presentado ya estaba revocado significa que se está
    reutilizando, así que se revoca la familia completa (la cadena de tokens
    rotados de esa sesión) y se corta la sesión.
    """
    revoked: list[models.RefreshToken] = []
    for token in candidates:
        token_data = decode_refresh_token(token)
        if token_data is None:
            continue
        jti = token_data.get("jti")
        if not jti:
            continue
        record = crud.get_refresh_token(db, jti)
        if record is None:
            continue
        if record.revoked_at is not None:
            # Solo un token rotado que vuelve a aparecer es reutilización; los
            # revocados por logout o por expiración ya están cerrados.
            if record.revoked_reason == REVOKE_ROTATED:
                revoked.append(record)
            continue
        return record, token_data

    if revoked:
        for record in revoked:
            crud.revoke_refresh_token_family(db, record.family_id, REVOKE_REUSE)
        raise _unauthorized(REUSE_DETAIL)
    return None, None


@router.post(
    "/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED
)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, payload.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado",
        )
    if crud.get_user_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado",
        )
    return crud.create_user(db, payload)


@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = crud.get_user_by_username(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario inactivo"
        )
    tokens = _issue_tokens(db, user, request)
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post("/refresh", response_model=schemas.Token)
def refresh(
    request: Request,
    response: Response,
    payload: schemas.RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    candidates = _candidate_tokens(request, payload)
    if not candidates:
        raise _unauthorized("Falta el refresh token")

    record, token_data = _resolve_refresh_record(db, candidates)
    if record is None or token_data is None:
        raise _unauthorized("Refresh token inválido o expirado")

    expires_at = crud.as_utc(record.expires_at)
    if expires_at is not None and expires_at <= utcnow():
        crud.revoke_refresh_token(db, record, REVOKE_EXPIRED)
        raise _unauthorized("Refresh token expirado")

    username = token_data.get("sub")
    if not username:
        raise _unauthorized("Refresh token inválido")

    user = crud.get_user_by_username(db, username)
    if user is None or not user.is_active:
        crud.revoke_refresh_token_family(db, record.family_id, REVOKE_LOGOUT)
        raise _unauthorized("Usuario no válido")

    tokens = _issue_tokens(
        db, user, request, family_id=record.family_id, rotate_from=record
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    payload: schemas.RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    for token in _candidate_tokens(request, payload):
        token_data = decode_refresh_token(token)
        if token_data is None:
            continue
        record = crud.get_refresh_token(db, token_data.get("jti"))
        if record is not None:
            crud.revoke_refresh_token_family(db, record.family_id, REVOKE_LOGOUT)
            break
    _clear_refresh_cookie(response)
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    request: Request,
    response: Response,
    payload: schemas.RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    for token in _candidate_tokens(request, payload):
        token_data = decode_refresh_token(token)
        if token_data is None:
            continue
        user = crud.get_user_by_username(db, token_data.get("sub"))
        if user is not None:
            crud.revoke_user_refresh_tokens(db, user.id, REVOKE_LOGOUT_ALL)
            break
    _clear_refresh_cookie(response)
    return None


@router.get("/sessions", response_model=list[schemas.SessionRead])
def list_sessions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = utcnow()
    sessions = []
    for record in crud.list_user_sessions(db, current_user.id):
        expires_at = crud.as_utc(record.expires_at)
        revoked_at = crud.as_utc(record.revoked_at)
        active = revoked_at is None and (expires_at is None or expires_at > now)
        sessions.append(
            schemas.SessionRead(
                jti=record.jti,
                issued_at=crud.as_utc(record.issued_at),
                expires_at=expires_at,
                revoked_at=revoked_at,
                revoked_reason=record.revoked_reason,
                user_agent=record.user_agent,
                client_ip=record.client_ip,
                active=active,
            )
        )
    return sessions


@router.get("/me", response_model=schemas.UserRead)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user

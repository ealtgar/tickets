from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models, schemas
from .security import hash_password, utcnow


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.scalar(select(models.User).where(models.User.username == username))


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.scalar(select(models.User).where(models.User.email == email))


def create_user(db: Session, data: schemas.UserCreate) -> models.User:
    user = models.User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(
    db: Session,
    *,
    search: str | None = None,
    role: models.UserRole | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[int, list[models.User]]:
    stmt = select(models.User)
    count_stmt = select(func.count()).select_from(models.User)

    filters = []
    if role is not None:
        filters.append(models.User.role == role)
    if is_active is not None:
        filters.append(models.User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                models.User.username.ilike(pattern),
                models.User.email.ilike(pattern),
            )
        )

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(models.User.created_at.desc()).offset(skip).limit(limit)
    items = list(db.scalars(stmt).all())
    return total, items


def delete_user(db: Session, user: models.User) -> None:
    """Elimina el usuario y sus sesiones.

    Los tickets no se borran: quedan sin propietario (`owner_id` a NULL) para
    no perder el histórico ni los comentarios asociados.
    """
    for ticket in user.tickets:
        ticket.owner_id = None
    db.delete(user)
    db.commit()


def list_tickets(
    db: Session,
    *,
    status: models.TicketStatus | None = None,
    priority: models.TicketPriority | None = None,
    search: str | None = None,
    owner_id: int | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[int, list[models.Ticket]]:
    stmt = select(models.Ticket)
    count_stmt = select(func.count()).select_from(models.Ticket)

    filters = []
    if status is not None:
        filters.append(models.Ticket.status == status)
    if priority is not None:
        filters.append(models.Ticket.priority == priority)
    if owner_id is not None:
        filters.append(models.Ticket.owner_id == owner_id)
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                models.Ticket.title.ilike(pattern),
                models.Ticket.description.ilike(pattern),
            )
        )

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(models.Ticket.created_at.desc()).offset(skip).limit(limit)
    items = list(db.scalars(stmt).all())
    return total, items


def get_ticket(db: Session, ticket_id: int) -> models.Ticket | None:
    return db.get(models.Ticket, ticket_id)


def create_ticket(db: Session, data: schemas.TicketCreate, owner_id: int | None = None) -> models.Ticket:
    ticket = models.Ticket(**data.model_dump(), owner_id=owner_id)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket(
    db: Session, ticket: models.Ticket, data: schemas.TicketUpdate
) -> models.Ticket:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket: models.Ticket) -> None:
    db.delete(ticket)
    db.commit()


def list_comments(db: Session, ticket_id: int) -> list[models.Comment]:
    stmt = (
        select(models.Comment)
        .where(models.Comment.ticket_id == ticket_id)
        .order_by(models.Comment.created_at)
    )
    return list(db.scalars(stmt).all())


def create_comment(
    db: Session, ticket_id: int, data: schemas.CommentCreate
) -> models.Comment:
    comment = models.Comment(ticket_id=ticket_id, **data.model_dump())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def get_comment(db: Session, comment_id: int) -> models.Comment | None:
    return db.get(models.Comment, comment_id)


def delete_comment(db: Session, comment: models.Comment) -> None:
    db.delete(comment)
    db.commit()


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes naive; los tratamos siempre como UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def create_refresh_token(
    db: Session,
    *,
    user: models.User,
    jti: str,
    family_id: str,
    expires_at: datetime,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> models.RefreshToken:
    record = models.RefreshToken(
        jti=jti,
        user_id=user.id,
        family_id=family_id,
        issued_at=utcnow(),
        expires_at=expires_at,
        user_agent=user_agent,
        client_ip=client_ip,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_refresh_token(db: Session, jti: str) -> models.RefreshToken | None:
    return db.scalar(
        select(models.RefreshToken).where(models.RefreshToken.jti == jti)
    )


def revoke_refresh_token(
    db: Session,
    record: models.RefreshToken,
    reason: str,
    replaced_by_jti: str | None = None,
) -> models.RefreshToken:
    if record.revoked_at is None:
        record.revoked_at = utcnow()
        record.revoked_reason = reason
        if replaced_by_jti:
            record.replaced_by_jti = replaced_by_jti
        db.commit()
        db.refresh(record)
    return record


def revoke_refresh_token_family(
    db: Session, family_id: str, reason: str
) -> int:
    """Revoca todos los tokens vivos de una familia (sesión)."""
    records = db.scalars(
        select(models.RefreshToken).where(
            models.RefreshToken.family_id == family_id,
            models.RefreshToken.revoked_at.is_(None),
        )
    ).all()
    now = utcnow()
    for record in records:
        record.revoked_at = now
        record.revoked_reason = reason
    if records:
        db.commit()
    return len(records)


def revoke_user_refresh_tokens(db: Session, user_id: int, reason: str) -> int:
    """Revoca todas las sesiones activas de un usuario."""
    records = db.scalars(
        select(models.RefreshToken).where(
            models.RefreshToken.user_id == user_id,
            models.RefreshToken.revoked_at.is_(None),
        )
    ).all()
    now = utcnow()
    for record in records:
        record.revoked_at = now
        record.revoked_reason = reason
    if records:
        db.commit()
    return len(records)


def list_user_sessions(db: Session, user_id: int) -> list[models.RefreshToken]:
    return list(
        db.scalars(
            select(models.RefreshToken)
            .where(models.RefreshToken.user_id == user_id)
            .order_by(models.RefreshToken.issued_at.desc())
        ).all()
    )


def purge_expired_refresh_tokens(db: Session) -> int:
    """Elimina los tokens expirados o revocados hace tiempo."""
    now = utcnow()
    records = db.scalars(
        select(models.RefreshToken).where(
            models.RefreshToken.expires_at < now.replace(tzinfo=None)
        )
    ).all()
    for record in records:
        db.delete(record)
    if records:
        db.commit()
    return len(records)
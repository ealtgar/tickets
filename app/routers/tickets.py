from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..deps import (
    get_current_active_user,
    require_admin,
    require_manager_or_admin,
)

router = APIRouter(
    prefix="/api/tickets",
    tags=["tickets"],
)


def get_ticket_or_404(ticket_id: int, db: Session) -> models.Ticket:
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado"
        )
    return ticket


def _is_admin(user: models.User) -> bool:
    return user.role == models.UserRole.admin or user.is_superuser


def _is_manager(user: models.User) -> bool:
    return user.role == models.UserRole.manager


@router.get("", response_model=schemas.TicketList)
def list_tickets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    status_: models.TicketStatus | None = Query(None, alias="status"),
    priority: models.TicketPriority | None = Query(None),
    search: str | None = Query(None, description="Busca en título y descripción"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    if _is_admin(current_user) or _is_manager(current_user):
        owner_id = None
    else:
        owner_id = current_user.id
    total, items = crud.list_tickets(
        db,
        status=status_,
        priority=priority,
        search=search,
        owner_id=owner_id,
        skip=skip,
        limit=limit,
    )
    return schemas.TicketList(total=total, skip=skip, limit=limit, items=items)


@router.post("", response_model=schemas.TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    return crud.create_ticket(db, payload, owner_id=current_user.id)


@router.get("/{ticket_id}", response_model=schemas.TicketDetail)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    ticket = get_ticket_or_404(ticket_id, db)
    if _is_admin(current_user) or _is_manager(current_user):
        return ticket
    if ticket.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver este ticket",
        )
    return ticket


@router.patch("/{ticket_id}", response_model=schemas.TicketRead)
def update_ticket(
    ticket_id: int,
    payload: schemas.TicketUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_manager_or_admin),
):
    ticket = get_ticket_or_404(ticket_id, db)
    return crud.update_ticket(db, ticket, payload)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    ticket = get_ticket_or_404(ticket_id, db)
    crud.delete_ticket(db, ticket)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..deps import get_current_active_user, require_admin

router = APIRouter(
    prefix="/api/tickets",
    tags=["comments"],
)


def _is_admin(user: models.User) -> bool:
    return user.role == models.UserRole.admin or user.is_superuser


def _is_manager(user: models.User) -> bool:
    return user.role == models.UserRole.manager


def _check_ticket_access(ticket: models.Ticket, current_user: models.User) -> None:
    if _is_admin(current_user) or _is_manager(current_user):
        return
    if ticket.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a este ticket",
        )


@router.get("/{ticket_id}/comments", response_model=list[schemas.CommentRead])
def list_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado"
        )
    _check_ticket_access(ticket, current_user)
    return crud.list_comments(db, ticket_id)


@router.post("/{ticket_id}/comments", response_model=schemas.CommentRead, status_code=status.HTTP_201_CREATED)
def create_comment(
    ticket_id: int,
    payload: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado"
        )
    _check_ticket_access(ticket, current_user)
    return crud.create_comment(db, ticket_id, payload)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    comment = crud.get_comment(db, comment_id)
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comentario no encontrado"
        )
    crud.delete_comment(db, comment)
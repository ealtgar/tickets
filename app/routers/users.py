from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..deps import require_admin

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)


def get_user_or_404(user_id: int, db: Session) -> models.User:
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )
    return user


@router.get("", response_model=schemas.UserList)
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
    search: str | None = Query(None, description="Busca por username o email"),
    role: models.UserRole | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    total, items = crud.list_users(
        db,
        search=search,
        role=role,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return schemas.UserList(total=total, skip=skip, limit=limit, items=items)


@router.get("/{user_id}", response_model=schemas.UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    return get_user_or_404(user_id, db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = get_user_or_404(user_id, db)
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propio usuario",
        )
    crud.delete_user(db, user)

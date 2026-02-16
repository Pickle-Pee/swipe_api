from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from common.models import User, Admin
from .. import schemas
from ..dependencies import get_current_admin, get_db

router = APIRouter(
    tags=["users"],
    dependencies=[Depends(get_current_admin)]
)


@router.get("/", response_model=List[schemas.UserResponse], summary="Получение списка пользователей")
def get_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/{user_id}", response_model=schemas.UserResponse, summary="Получение информации о конкретном пользователе")
def get_user(user_id: int, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user

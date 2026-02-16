from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from common.models import Interest
from .. import schemas
from ..dependencies import get_current_admin, get_db

router = APIRouter(
    tags=["interests"],
    dependencies=[Depends(get_current_admin)]
)


@router.get("/", response_model=List[schemas.InterestResponse], summary="Получение списка интересов")
def get_interests(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    interests = db.query(Interest).offset(skip).limit(limit).all()
    return interests


@router.get("/{interest_id}", response_model=schemas.InterestResponse,
            summary="Получение информации о конкретном интересе")
def get_interest(interest_id: int, db: Session = Depends(get_db)):
    interest = db.query(Interest).filter(Interest.id == interest_id).first()
    if not interest:
        raise HTTPException(status_code=404, detail="Интерес не найден")
    return interest

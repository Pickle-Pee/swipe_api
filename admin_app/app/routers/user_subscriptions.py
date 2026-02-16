from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from common.models import UserSubscription
from .. import schemas
from ..dependencies import get_current_admin, get_db

router = APIRouter(
    tags=["user_subscriptions"],
    dependencies=[Depends(get_current_admin)]
)


@router.get("/", response_model=List[schemas.SubscriptionResponse], summary="Получение списка подписок пользователей")
def get_user_subscriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    user_subscriptions = db.query(UserSubscription).offset(skip).limit(limit).all()
    return user_subscriptions

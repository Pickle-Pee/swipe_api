from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from common.models import Subscription
from .. import schemas
from ..dependencies import get_current_admin, get_db

router = APIRouter(
    tags=["subscriptions"],
    dependencies=[Depends(get_current_admin)]
)


@router.get("/", response_model=List[schemas.SubscriptionResponse], summary="Получение списка подписок")
def get_subscriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    subscriptions = db.query(Subscription).offset(skip).limit(limit).all()
    return subscriptions


@router.get("/{subscription_id}", response_model=schemas.SubscriptionResponse,
            summary="Получение информации о конкретной подписке")
def get_subscription(subscription_id: int, db: Session = Depends(get_db)):
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Подписка не найдена")
    return subscription

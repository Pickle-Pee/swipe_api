from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from common.models import Transaction
from .. import schemas
from ..dependencies import get_current_admin, get_db

router = APIRouter(
    tags=["transactions"],
    dependencies=[Depends(get_current_admin)]
)


@router.get("/", response_model=List[schemas.TransactionResponse], summary="Получение списка транзакций")
def get_transactions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    transactions = db.query(Transaction).offset(skip).limit(limit).all()
    return transactions


@router.get("/{transaction_id}", response_model=schemas.TransactionResponse,
            summary="Получение информации о конкретной транзакции")
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Транзакция не найдена")
    return transaction

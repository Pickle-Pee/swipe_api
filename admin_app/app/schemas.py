from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, date


# Схема для Админа
class AdminCreate(BaseModel):
    username: str
    password: str
    email: EmailStr


class AdminResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


# Схема для Авторизации
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# Схема для Пользователей
class UserResponse(BaseModel):
    id: int
    phone_number: str
    first_name: Optional[str]
    last_name: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    is_subscription: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Схема для Подписок
class SubscriptionResponse(BaseModel):
    id: int
    name: str
    price: float
    duration: int
    features: str
    is_active: bool
    renewable: bool

    class Config:
        from_attributes = True


# Схема для Интересов
class InterestResponse(BaseModel):
    id: int
    interest_text: str

    class Config:
        from_attributes = True


# Схема для Транзакций
class TransactionResponse(BaseModel):
    id: int
    user_id: int
    subscription_id: int
    amount: float
    transaction_date: datetime
    order_number: str
    payment_id: int
    payment_url: Optional[str]
    status: str
    card_id: Optional[str]
    rebill_id: Optional[str]

    class Config:
        from_attributes = True

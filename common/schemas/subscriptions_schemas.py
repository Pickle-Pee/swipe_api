from pydantic import BaseModel, Field
from typing import Optional, List


class SubscriptionBase(BaseModel):
    id: int
    name: str
    price: float
    duration: int
    features: Optional[str] = None
    is_active: bool

    class Config:
        orm_mode = True


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionInDBBase(SubscriptionBase):
    id: int

    class Config:
        orm_mode = True


class SubscriptionSchema(SubscriptionInDBBase):
    pass


class SubscriptionsResponse(BaseModel):
    subscriptions: List[SubscriptionBase]


class TinkoffWebhook(BaseModel):
    TerminalKey: str = Field(..., alias="TerminalKey")
    OrderId: str = Field(..., alias="OrderId")
    Success: bool = Field(..., alias="Success")
    Status: str = Field(..., alias="Status")
    PaymentId: int = Field(..., alias="PaymentId")
    ErrorCode: str = Field(..., alias="ErrorCode")
    Amount: int = Field(..., alias="Amount")
    CardId: Optional[int] = Field(None, alias="CardId")
    Pan: Optional[str] = Field(None, alias="Pan")
    ExpDate: Optional[str] = Field(None, alias="ExpDate")
    Token: str = Field(..., alias="Token")
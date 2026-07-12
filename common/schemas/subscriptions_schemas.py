from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SubscriptionBase(BaseModel):
    id: int
    name: str
    price: float
    duration: int
    features: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionInDBBase(SubscriptionBase):
    id: int

    class Config:
        from_attributes = True


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


PaymentStatus = Literal[
    "pending",
    "requires_action",
    "processing",
    "succeeded",
    "failed",
    "canceled",
    "refunded",
    "partially_refunded",
]


class SubscriptionPlanResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price_minor: int
    currency: Literal["RUB"]
    duration_days: int
    is_active: bool
    renewable: bool


class SubscriptionPlansResponse(BaseModel):
    subscriptions: List[SubscriptionPlanResponse]


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription_id: int = Field(gt=0)


class CheckoutResponse(BaseModel):
    order_id: str
    payment_id: Optional[str] = None
    payment_url: Optional[HttpUrl] = None
    status: PaymentStatus
    amount_minor: int
    currency: Literal["RUB"]
    expires_at: Optional[datetime] = None


class ActiveSubscriptionResponseItem(BaseModel):
    subscription_id: int
    name: str
    start_at: datetime
    end_at: datetime
    renewable: bool


class ActiveSubscriptionResponse(BaseModel):
    subscription: Optional[ActiveSubscriptionResponseItem] = None


class PaymentStatusResponse(BaseModel):
    order_id: str
    payment_id: Optional[str] = None
    status: PaymentStatus
    subscription_activated: bool
    subscription: Optional[ActiveSubscriptionResponseItem] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    updated_at: datetime

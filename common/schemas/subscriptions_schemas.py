from pydantic import BaseModel
from typing import Optional


class SubscriptionBase(BaseModel):
    name: str
    price: float
    duration: int
    features: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionInDBBase(SubscriptionBase):
    id: int

    class Config:
        orm_mode = True


class SubscriptionSchema(SubscriptionInDBBase):
    pass

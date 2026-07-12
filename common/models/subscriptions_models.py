from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.orm import synonym
from datetime import datetime

from config import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    duration = Column(Integer)
    features = Column(String)
    price_minor = Column(BigInteger, nullable=True)
    currency = Column(String(3), nullable=False, default="RUB")
    duration_days = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean)
    renewable = Column(Boolean, default=True)

    user_subscriptions = relationship("UserSubscription", back_populates="subscription")
    transactions = relationship("Transaction", back_populates="subscription")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    next_billing_date = Column(DateTime, nullable=True)
    renewable = Column(Boolean, default=True)

    user = relationship("User", back_populates="subscriptions")
    subscription = relationship("Subscription", back_populates="user_subscriptions")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_transactions_user_idempotency_key"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    amount = Column(Float, nullable=False)
    amount_minor = Column(BigInteger, nullable=True)
    currency = Column(String(3), nullable=False, default="RUB")
    transaction_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    order_id = Column(String, nullable=False, unique=True)
    order_number = synonym("order_id")
    payment_id = Column(String, nullable=True, unique=True)
    payment_url = Column(String, nullable=True)
    status = Column(String, default="created", nullable=False)
    bank_status = Column(String, nullable=True)
    card_id = Column(String, nullable=True)
    rebill_id = Column(String, nullable=True)
    idempotency_key = Column(String(64), nullable=True)
    request_fingerprint = Column(String(64), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    confirmed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(255), nullable=True)

    user = relationship("User", back_populates="transactions")
    subscription = relationship("Subscription", back_populates="transactions")

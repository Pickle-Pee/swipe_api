from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime

from config import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    duration = Column(Integer)
    features = Column(String)
    is_active = Column(Boolean)
    renewable = Column(Boolean, default=True)

    user_subscriptions = relationship("UserSubscription", back_populates="subscription")
    transactions = relationship("Transaction", back_populates="subscription")


class UserSubscription(Base):
    __tablename__ = 'user_subscriptions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    subscription_id = Column(Integer, ForeignKey('subscriptions.id'), nullable=False)
    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    next_billing_date = Column(DateTime, nullable=True)
    renewable = Column(Boolean, default=True)

    user = relationship("User", back_populates="subscriptions")
    subscription = relationship("Subscription", back_populates="user_subscriptions")


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    subscription_id = Column(Integer, ForeignKey('subscriptions.id'), nullable=False)
    amount = Column(Float, nullable=False)
    transaction_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    order_number = Column(String, nullable=False, unique=True)
    payment_id = Column(BigInteger, nullable=False, unique=True)
    payment_url = Column(String, nullable=True)
    status = Column(String, default="INITIATED", nullable=False)
    card_id = Column(String, nullable=True)
    rebill_id = Column(String, nullable=True)

    user = relationship("User", back_populates="transactions")
    subscription = relationship("Subscription", back_populates="transactions")

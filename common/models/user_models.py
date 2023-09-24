from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from config import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    date_of_birth = Column(Date)
    gender = Column(String)
    verify = Column(Boolean)
    is_subscription = Column(Boolean)
    city_id = Column(Integer, ForeignKey('cities.id'))
    about_me = Column(Text)
    status = Column(Text)
    avatar_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    interests = relationship("UserInterest", back_populates="user")
    city = relationship("City")
    tokens = relationship("PushTokens", back_populates="user", cascade="all, delete-orphan")


class PushTokens(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="tokens")

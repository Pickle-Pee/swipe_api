from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from config import Base


class TemporaryCode(Base):
    __tablename__ = "temporary_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, index=True)
    code = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, index=True)
    refresh_token = Column(String, unique=True, index=True)

    user = relationship("User", back_populates="refresh_tokens")
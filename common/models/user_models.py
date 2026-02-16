from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text, Float, func, Enum, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from common.models.enums import VerificationStatusEnum, SmokingAttitudeEnum, AlcoholAttitudeEnum, WhatLookingForEnum, \
    ReligionEnum, AppearanceEnum, ChildrenEnum
from config import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    date_of_birth = Column(Date)
    gender = Column(String)
    verify = Column(String, default=str(VerificationStatusEnum.DENIED))
    is_subscription = Column(Boolean, default=False)
    city_id = Column(Integer, ForeignKey('cities.id'))
    about_me = Column(Text)
    status = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    deleted = Column(Boolean, default=False)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    interests = relationship("UserInterest", back_populates="user")
    city = relationship("City")
    tokens = relationship("PushTokens", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="sender", lazy="dynamic")
    photos = relationship("UserPhoto", back_populates="user")
    user_geolocation = relationship("UserGeolocation", back_populates="user", uselist=False)
    verification = relationship('VerificationQueue', back_populates='user')
    subscriptions = relationship("UserSubscription", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    attributes = relationship("UserAttributes", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserAttributes(Base):
    __tablename__ = "user_attributes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    height = Column(Integer, nullable=True)
    smoking_attitude = Column(Enum(SmokingAttitudeEnum), nullable=True)
    alcohol_attitude = Column(Enum(AlcoholAttitudeEnum), nullable=True)
    children_preference = Column(Enum(ChildrenEnum), nullable=True)
    what_looking_for = Column(Enum(WhatLookingForEnum), nullable=True)
    appearance = Column(Enum(AppearanceEnum), nullable=True)
    religion = Column(Enum(ReligionEnum), nullable=True)

    user = relationship("User", back_populates="attributes")

    __table_args__ = (
        Index('idx_height', 'height'),
        Index('idx_smoking_attitude', 'smoking_attitude'),
        Index('idx_alcohol_attitude', 'alcohol_attitude'),
        Index('idx_children_preference', 'children_preference'),
        Index('idx_what_looking_for', 'what_looking_for'),
        Index('idx_religion', 'religion'),
    )


class PushTokens(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="tokens")


class UserPhoto(Base):
    __tablename__ = 'user_photos'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    photo_url = Column(String, nullable=False)
    is_avatar = Column(Boolean, default=False)

    # Новые поля для сохранения масштаба и позиции изображения
    scale = Column(Float, default=1.0)
    position_x = Column(Float, default=0.0)
    position_y = Column(Float, default=0.0)

    user = relationship("User", back_populates="photos")

    def set_as_avatar(self, session):
        session.query(UserPhoto).filter(
            UserPhoto.user_id == self.user_id
        ).update({UserPhoto.is_avatar: False})

        self.is_avatar = True
        session.commit()


class UserGeolocation(Base):
    __tablename__ = 'user_geolocation'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, nullable=False)

    user = relationship("User", back_populates="user_geolocation")


class VerificationQueue(Base):
    __tablename__ = 'verification_queue'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    photo1 = Column(String, nullable=False)
    photo2 = Column(String, nullable=False)
    status = Column(String, default='pending', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="verification")

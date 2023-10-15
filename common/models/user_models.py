from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text, Float, func
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    interests = relationship("UserInterest", back_populates="user")
    city = relationship("City")
    tokens = relationship("PushTokens", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="sender", lazy="dynamic")
    photos = relationship("UserPhoto", back_populates="user")
    user_geolocation = relationship("UserGeolocation", back_populates="user", uselist=False)


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

    # user = relationship("User", back_populates="verification")
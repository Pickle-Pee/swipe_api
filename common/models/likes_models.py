from sqlalchemy import Column, Integer, DateTime, ForeignKey, Boolean
from datetime import datetime

from sqlalchemy.orm import relationship

from config import Base


class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    liked_user_id = Column(Integer, ForeignKey('users.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    mutual = Column(Boolean, default=False)


class Dislike(Base):
    __tablename__ = "dislikes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    disliked_user_id = Column(Integer, ForeignKey('users.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)


class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    favorite_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    favorite_user = relationship("User", foreign_keys=[favorite_user_id])
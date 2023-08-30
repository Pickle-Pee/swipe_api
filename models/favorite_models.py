from config import Base
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship


class Favorite(Base):
    __tablename__ = 'favorites'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    favorite_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    favorite_user = relationship("User", foreign_keys=[favorite_user_id])

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from config import Base


class Interest(Base):
    __tablename__ = 'interests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    interest_text = Column(String, nullable=False)


class UserInterest(Base):
    __tablename__ = 'user_interests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    interest_id = Column(Integer, ForeignKey('interests.id'), nullable=False)

    user = relationship("User", back_populates="interests")
    interest = relationship("Interest")

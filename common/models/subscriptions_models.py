from sqlalchemy import Column, Integer, String, Float

from config import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    duration = Column(Integer)
    features = Column(String)

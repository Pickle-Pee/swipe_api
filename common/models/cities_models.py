from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from config import Base


class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    cities = relationship("City", back_populates="region")


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    city_name = Column(String, index=True)
    region_id = Column(Integer, ForeignKey('regions.id'), index=True)

    region = relationship("Region", back_populates="cities")

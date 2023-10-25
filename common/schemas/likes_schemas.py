from typing import Optional
from datetime import date
from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    user_id: int
    favorite_user_id: int


class Favorite(FavoriteCreate):
    id: int

    class Config:
        orm_mode = True


class MatchResponse(BaseModel):
    user_id: int
    first_name: str
    date_of_birth: date
    gender: str
    status: Optional[str] = None
    city_name: Optional[str] = None
    avatar_url: Optional[str] = None

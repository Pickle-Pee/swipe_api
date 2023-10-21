from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    user_id: int
    favorite_user_id: int


class Favorite(FavoriteCreate):
    id: int

    class Config:
        orm_mode = True

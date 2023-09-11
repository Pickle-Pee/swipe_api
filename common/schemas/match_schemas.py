from typing import Optional
from pydantic import BaseModel
from datetime import date


class MatchResponse(BaseModel):
    user_id: int
    first_name: str
    date_of_birth: date
    gender: str
    status: str
    city_name: Optional[str] = None
    avatar_url: Optional[str] = None

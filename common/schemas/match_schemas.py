from typing import Optional

from pydantic import BaseModel
from datetime import date


class MatchResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    verify: bool = False
    city: Optional[str] = None
    match_percentage: int = 0
    score: int

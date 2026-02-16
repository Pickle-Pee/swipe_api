from typing import List
from pydantic import BaseModel


class AddInterestsRequest(BaseModel):
    interest_ids: List[int]

    class Config:
        from_attributes = True


class AddInterestsResponse(BaseModel):
    message: str

    class Config:
        from_attributes = True


class InterestCreate(BaseModel):
    interest_text: str


class Interest(InterestCreate):
    id: int
    interest_text: str

    class Config:
        from_attributes = True


class InterestResponse(BaseModel):
    interests: List[Interest]

    class Config:
        from_attributes = True


class InterestItem(BaseModel):
    id: int
    interest_text: str


class UserInterestResponse(BaseModel):
    user_id: int
    interests: List[InterestItem]


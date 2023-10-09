from datetime import date, datetime
from pydantic import BaseModel, field_validator
from typing import Optional, List, Tuple


class UserCreate(BaseModel):
    phone_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    verify: bool = False
    city_name: str
    status: str = "offline"

    @field_validator("phone_number")
    def validate_phone_number(cls, value):
        if not value.isdigit():
            raise ValueError("Phone number must consist only of digits")
        if len(value) != 11:
            raise ValueError("Phone number must be 11 digits long")
        if value[0] != "7":
            raise ValueError("First digit of phone number must be 7")
        return value


class UserResponse(UserCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class UserIdResponse(BaseModel):
    id: int
    verify: bool
    created_at: datetime
    updated_at: datetime


class UserDataResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    verify: bool
    is_subscription: bool
    city_name: Optional[str] = None
    is_favorite: Optional[bool] = False
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    interests: Optional[List[Tuple[int, str]]] = None
    match_percentage: Optional[int] = None


class InterestResponse(BaseModel):
    interest_id: int
    interest_text: str


class PersonalUserDataResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    verify: bool
    is_subscription: bool
    city_name: Optional[str] = None
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    interests: Optional[List[InterestResponse]] = None


class UserLikesResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    city_name: Optional[str] = None
    is_favorite: Optional[bool] = False
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    match_percentage: Optional[int] = None


class AddTokenRequest(BaseModel):
    token: str


class UpdateUserRequest(BaseModel):
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    city_name: Optional[str] = None
    about_me: Optional[str] = None


class UpdateUserResponse(BaseModel):
    message: str


class UserPhotoCreate(BaseModel):
    photo_url: str
    is_avatar: bool


class UserPhotoInDB(UserPhotoCreate):
    id: int

    class Config:
        orm_mode = True


class UserPhotoResponse(BaseModel):
    id: int
    photo_url: str
    is_avatar: bool

    class Config:
        orm_mode = True


class UserPhotosResponse(BaseModel):
    photos: List[UserPhotoResponse]


class AddGeolocationRequest(BaseModel):
    latitude: float
    longitude: float
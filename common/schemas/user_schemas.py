from datetime import date, datetime
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal

class UserCreate(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    phone_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    verify: Literal["denied", "approved", "in_progress"] = Field(default="denied")
    city_name: str
    status: str = "offline"

    @validator("phone_number")
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
    gender: str
    is_subscription: bool
    created_at: datetime
    updated_at: datetime

class InterestResponseUser(BaseModel):
    interest_id: int
    interest_text: str


class UserDataResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    is_subscription: bool
    city_name: Optional[str] = None
    is_favorite: Optional[bool]
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    interests: Optional[List[InterestResponseUser]] = None
    match_percentage: Optional[int] = None


class PersonalUserDataResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    is_subscription: bool
    city_name: Optional[str] = None
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    interests: Optional[List[InterestResponseUser]] = None
    deleted: Optional[bool]


class UserLikesResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    city_name: Optional[str] = None
    is_favorite: Optional[bool] = None
    about_me: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None
    match_percentage: Optional[float] = None
    mutual: Optional[bool] = None


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

class UserResponseAdmin(BaseModel):
    id: int
    phone_number: str
    created_at: datetime
    updated_at: datetime
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    verify: str
    is_subscription: bool
    city_name: Optional[str] = None
    about_me: Optional[str] = None
    status: Optional[str] = None
    deleted: Optional[bool]


class UsersResponse(BaseModel):
    users: List[UserResponseAdmin]

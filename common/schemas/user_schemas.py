# schemas/user.py

from datetime import date, datetime
from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional, List

from common.models.enums import VerificationStatusEnum, SmokingAttitudeEnum, AlcoholAttitudeEnum, WhatLookingForEnum, \
    ReligionEnum, AppearanceEnum, ChildrenEnum


class AttributesResponseUser(BaseModel):
    height: Optional[int] = Field(None, description="Рост пользователя в сантиметрах")
    smoking_attitude: Optional[SmokingAttitudeEnum] = Field(None, description="Отношение к курению")
    alcohol_attitude: Optional[AlcoholAttitudeEnum] = Field(None, description="Отношение к алкоголю")
    children_preference: Optional[ChildrenEnum] = Field(None, description="Предпочтение относительно детей")
    what_looking_for: Optional[WhatLookingForEnum] = Field(None, description="Цель использования приложения")
    appearance: Optional[AppearanceEnum] = Field(None, description="Описание внешности")
    religion: Optional[ReligionEnum] = Field(None, description="Религиозные убеждения")

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    phone_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    verify: VerificationStatusEnum = Field(default=VerificationStatusEnum.DENIED)
    city_name: str
    status: str = "offline"
    attributes: Optional[AttributesResponseUser] = None

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
    attributes: Optional[AttributesResponseUser] = None


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
    attributes: Optional[AttributesResponseUser] = None

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
    attributes: Optional[AttributesResponseUser] = None


class AddTokenRequest(BaseModel):
    token: str


class UpdateUserRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    city_name: Optional[str] = None
    about_me: Optional[str] = None
    attributes: Optional[AttributesResponseUser] = None


class AddUserAttributesRequest(BaseModel):
    height: Optional[int] = Field(None, description="Рост пользователя в сантиметрах")
    smoking_attitude: Optional[SmokingAttitudeEnum] = Field(None, description="Отношение к курению")
    alcohol_attitude: Optional[AlcoholAttitudeEnum] = Field(None, description="Отношение к алкоголю")
    children_preference: Optional[ChildrenEnum] = Field(None, description="Предпочтение относительно детей")
    what_looking_for: Optional[WhatLookingForEnum] = Field(None, description="Цель использования приложения")
    appearance: Optional[AppearanceEnum] = Field(None, description="Описание внешности")
    religion: Optional[ReligionEnum] = Field(None, description="Религиозные убеждения")


class UpdateUserAttributesRequest(BaseModel):
    height: Optional[int] = Field(None, description="Рост пользователя в сантиметрах")
    smoking_attitude: Optional[SmokingAttitudeEnum] = Field(None, description="Отношение к курению")
    alcohol_attitude: Optional[AlcoholAttitudeEnum] = Field(None, description="Отношение к алкоголю")
    children_preference: Optional[ChildrenEnum] = Field(None, description="Предпочтение относительно детей")
    what_looking_for: Optional[WhatLookingForEnum] = Field(None, description="Цель использования приложения")
    appearance: Optional[AppearanceEnum] = Field(None, description="Описание внешности")
    religion: Optional[ReligionEnum] = Field(None, description="Религиозные убеждения")


class UserAttributesResponse(BaseModel):
    height: Optional[int] = Field(None, description="Рост пользователя в сантиметрах")
    smoking_attitude: Optional[SmokingAttitudeEnum] = Field(None, description="Отношение к курению")
    alcohol_attitude: Optional[AlcoholAttitudeEnum] = Field(None, description="Отношение к алкоголю")
    children_preference: Optional[ChildrenEnum] = Field(None, description="Предпочтение относительно детей")
    what_looking_for: Optional[WhatLookingForEnum] = Field(None, description="Цель использования приложения")
    appearance: Optional[AppearanceEnum] = Field(None, description="Описание внешности")
    religion: Optional[ReligionEnum] = Field(None, description="Религиозные убеждения")

    model_config = ConfigDict(from_attributes=True)


class UpdateUserResponse(BaseModel):
    message: str


class UserPhotoCreate(BaseModel):
    photo_url: str
    is_avatar: bool


class UserPhotoInDB(UserPhotoCreate):
    id: int


class UserPhotoResponse(BaseModel):
    id: int
    photo_url: str
    is_avatar: bool
    scale: Optional[float] = 1.0
    position_x: Optional[float] = 0.0
    position_y: Optional[float] = 0.0


class UserPhotosResponse(BaseModel):
    photos: List[UserPhotoResponse]


class AddGeolocationRequest(BaseModel):
    latitude: float
    longitude: float


class UsersResponseAdmin(BaseModel):
    id: int
    phone_number: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    city_name: Optional[str] = None
    deleted: Optional[bool]


class UsersResponse(BaseModel):
    users: List[UsersResponseAdmin]


class UserResponseAdmin(BaseModel):
    id: int
    phone_number: str
    created_at: datetime
    updated_at: datetime
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    verify: VerificationStatusEnum
    is_subscription: bool
    city_name: Optional[str] = None
    about_me: Optional[str] = None
    status: Optional[str] = None
    deleted: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

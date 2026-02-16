from enum import Enum as PyEnum
from pydantic import BaseModel, Field


class CityQuery(BaseModel):
    query: str


class VerificationStatus(str, PyEnum):
    approved = "approved"
    denied = "denied"


class VerificationUpdate(BaseModel):
    status: VerificationStatus = Field(..., description="The new verification status")


class EnumItem(BaseModel):
    name: str
    description: str

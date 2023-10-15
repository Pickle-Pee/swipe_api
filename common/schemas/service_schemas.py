from enum import Enum

from pydantic import BaseModel, Field


class CityQuery(BaseModel):
    query: str

class VerificationStatus(str, Enum):
    approved = "approved"
    denied = "denied"

class VerificationUpdate(BaseModel):
    status: VerificationStatus = Field(..., description="The new verification status")
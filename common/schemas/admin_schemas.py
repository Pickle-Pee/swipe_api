from datetime import datetime

from pydantic import BaseModel

class AdminBase(BaseModel):
    username: str

class AdminCreate(AdminBase):
    password: str
    email: str

class Admin(AdminBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str
    admin_id: int

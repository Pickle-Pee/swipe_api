import datetime
import enum
from typing import Optional, List

from pydantic import BaseModel


class MessageTypeEnum(enum.Enum):
    text = "text"
    voice = "voice"
    image = "image"


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    content: str

    class Config:
        orm_mode = True


class ChatResponse(BaseModel):
    id: int
    user1_id: int
    user2_id: int

    class Config:
        orm_mode = True


class SendMessageRequest(BaseModel):
    chat_id: int
    content: str


class CreateChatRequest(BaseModel):
    user_id: int


class CreateChatResponse(BaseModel):
    chat_id: int


class SendMessageResponse(BaseModel):
    message_id: int


class UserInChat(BaseModel):
    user_id: int
    first_name: str
    user_age: int
    avatar_url: Optional[str]
    status: Optional[str]


class DateInvitationResponse(BaseModel):
    id: int
    sender_id: int
    status: str


class ChatPersonResponse(BaseModel):
    chat_id: int
    user: UserInChat
    created_at: datetime.datetime
    last_message: Optional[str] = None
    unread_count: Optional[int] = 0
    last_message_status: Optional[int] = None
    last_message_sender_id: Optional[int]
    last_message_type: Optional[MessageTypeEnum]
    date_invitations: List[DateInvitationResponse] = []


class ChatDetailsResponse(BaseModel):
    user_id: int
    first_name: str
    user_age: int
    avatar_url: Optional[str]
    status: Optional[str]

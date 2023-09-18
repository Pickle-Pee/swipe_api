import datetime
from pydantic import BaseModel


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
    userId: int
    first_name: str
    status: str
    avatar_url: str


class ChatPersonResponse(BaseModel):
    chatId: int
    user: UserInChat
    created_at: datetime.datetime



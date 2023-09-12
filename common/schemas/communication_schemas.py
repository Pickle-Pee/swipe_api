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



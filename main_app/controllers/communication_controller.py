from typing import List

from common.models.communication_models import Chat, Message
from fastapi import Depends, APIRouter, HTTPException

from common.schemas.communication_schemas import MessageResponse, ChatResponse
from config import SessionLocal, SECRET_KEY
from common.utils.auth_utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/communication", tags=["Communication Controller"])


@router.post("/create_chat", summary="Создать чат с пользователем")
def create_chat(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user_id = get_user_id_from_token(access_token, SECRET_KEY)
            new_chat = Chat(user1_id=current_user_id, user2_id=user_id)
            db.add(new_chat)
            db.commit()
            return {"chat_id": new_chat.id}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/send_message", summary="Отправить сообщение")
def send_message(chat_id: int, content: str, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user = get_user_id_from_token(access_token, SECRET_KEY)
            new_message = Message(chat_id=chat_id, sender_id=current_user, content=content)
            db.add(new_message)
            db.commit()
            return {"message_id": new_message.id}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/get_messages", response_model=List[MessageResponse], summary="Получить все сообщения в чате")
def get_messages(chat_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user = get_user_id_from_token(access_token, SECRET_KEY)
        messages = db.query(Message).filter(Message.chat_id == chat_id).all()
        return messages


@router.get("/get_chats", response_model=List[ChatResponse], summary="Получить все чаты")
def get_chats(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user = get_user_id_from_token(access_token, SECRET_KEY)
        chats = db.query(Chat).filter((Chat.user1_id == current_user) | (Chat.user2_id == current_user)).all()
        return chats



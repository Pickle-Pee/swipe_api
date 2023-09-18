from typing import List

from common.models.communication_models import Chat
from fastapi import Depends, APIRouter, HTTPException

from common.models.user_models import User
from common.schemas.communication_schemas import CreateChatRequest, \
    CreateChatResponse, UserInChat, ChatPersonResponse
from config import SessionLocal, SECRET_KEY
from common.utils.auth_utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/communication", tags=["Communication Controller"])


@router.post("/create_chat", summary="Создать чат с пользователем", response_model=CreateChatResponse)
def create_chat(request: CreateChatRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user_id = get_user_id_from_token(access_token, SECRET_KEY)

            # Проверяем, существует ли уже чат между этими пользователями
            existing_chat = db.query(Chat).filter(
                ((Chat.user1_id == current_user_id) & (Chat.user2_id == request.user_id)) |
                ((Chat.user1_id == request.user_id) & (Chat.user2_id == current_user_id))
            ).first()

            if existing_chat:
                return {"chat_id": existing_chat.id}

            # Если чата нет, создаем новый
            new_chat = Chat(user1_id=current_user_id, user2_id=request.user_id)
            db.add(new_chat)
            db.commit()
            return {"chat_id": new_chat.id}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/get_chats", response_model=List[ChatPersonResponse], summary="Получить все чаты")
def get_chats(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user = get_user_id_from_token(access_token, SECRET_KEY)
        chats = db.query(Chat).filter((Chat.user1_id == current_user) | (Chat.user2_id == current_user)).all()

        chat_responses = []
        for chat in chats:
            user2 = db.query(User).filter(User.id == chat.user2_id).first()

            user2_data = UserInChat(
                id=user2.id,
                first_name=user2.first_name,
                status=user2.status,
                avatar_url=user2.avatar_url
            )

            chat_response = ChatPersonResponse(
                id=chat.id,
                user2=user2_data,
                created_at=chat.created_at
            )

            chat_responses.append(chat_response)

        return chat_responses



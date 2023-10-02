from datetime import date
from typing import List

from common.models.communication_models import Chat, Message
from fastapi import Depends, APIRouter, HTTPException

from common.models.user_models import User
from common.schemas.communication_schemas import CreateChatRequest, \
    CreateChatResponse, UserInChat, ChatPersonResponse, ChatDetailsResponse
from config import SessionLocal
from common.utils.auth_utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/communication", tags=["Communication Controller"])


@router.post("/create_chat", summary="Создать чат с пользователем", response_model=CreateChatResponse)
def create_chat(request: CreateChatRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user_id = get_user_id_from_token(access_token)

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
    status_mapping = {
        'delivered': 1,
        'read': 2,
    }
    with SessionLocal() as db:
        current_user = get_user_id_from_token(access_token)
        chats = db.query(Chat).filter(
            ((Chat.user1_id == current_user) & (Chat.deleted_for_user1.is_(False))) |
            ((Chat.user2_id == current_user) & (Chat.deleted_for_user2.is_(False)))
        ).all()

        chat_responses = []
        for chat in chats:
            other_user_id = chat.user2_id if chat.user1_id == current_user else chat.user1_id
            user = db.query(User).filter(User.id == other_user_id).first()

            today = date.today()
            age = today.year - user.date_of_birth.year - ((today.month, today.day) < (user.date_of_birth.month,
                                                                                      user.date_of_birth.day))

            user2_data = UserInChat(
                user_id=user.id,
                first_name=user.first_name,
                user_age=age,
                status=user.status,
                avatar_url=user.avatar_url if user.avatar_url is not None else None,
            )

            # Получить последнее сообщение в чате
            last_message = db.query(Message).filter(Message.chat_id == chat.id).order_by(
                Message.created_at.desc()
                ).first()
            last_message_content = last_message.content if last_message else None
            last_message_status = status_mapping.get(last_message.status, None) if last_message else None
            last_message_sender_id = last_message.sender_id if last_message else None

            # Получить количество непрочитанных сообщений
            unread_count = db.query(Message).filter(
                Message.chat_id == chat.id,
                Message.status != 'read',
                Message.sender_id != current_user
            ).count()

            chat_response = ChatPersonResponse(
                chat_id=chat.id,
                user=user2_data,
                created_at=chat.created_at,
                last_message=last_message_content,
                unread_count=unread_count,
                last_message_status=last_message_status,
                last_message_sender_id=last_message_sender_id
            )

            chat_responses.append(chat_response)

        return chat_responses


@router.get("/{chat_id}", response_model=ChatDetailsResponse, summary="Получить детали чата")
def get_chat_details(chat_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        # Проверяем, существует ли чат с данным ID
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Убедимся, что текущий пользователь является участником чата
        if chat.user1_id != current_user_id and chat.user2_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this chat")

        # Получаем информацию о втором пользователе в чате
        other_user_id = chat.user1_id if chat.user1_id != current_user_id else chat.user2_id
        user = db.query(User).filter(User.id == other_user_id).first()

        # Вычисляем возраст пользователя
        today = date.today()
        age = today.year - user.date_of_birth.year - ((today.month, today.day) < (user.date_of_birth.month,
                                                                                  user.date_of_birth.day))

        # Формируем ответ
        chat_details = ChatDetailsResponse(
            user_id=user.id,
            first_name=user.first_name,
            user_age=age,
            avatar_url=user.avatar_url if user.avatar_url is not None else None,
            status=user.status if user.status is not None else None
        )

        return chat_details
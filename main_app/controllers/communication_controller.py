from datetime import date
from typing import List
from fastapi import Depends, APIRouter, HTTPException
from common.models import Chat, Message, DateInvitations, User, UserPhoto, PushTokens
from common.schemas import (
    CreateChatRequest,
    CreateChatResponse,
    UserInChat,
    ChatPersonResponse,
    ChatDetailsResponse,
    DateInvitationResponse, AddTokenRequest, ChatIdResponse
)
from common.utils import get_token, get_user_id_from_token
from config import SessionLocal

router = APIRouter(prefix="/communication", tags=["Communication Controller"])


@router.post("/create_chat", summary="Создать чат с пользователем", response_model=CreateChatResponse)
def create_chat(request: CreateChatRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user_id = get_user_id_from_token(access_token)

            existing_chat = db.query(Chat).filter(
                ((Chat.user1_id == current_user_id) & (Chat.user2_id == request.user_id)) |
                ((Chat.user1_id == request.user_id) & (Chat.user2_id == current_user_id))
            ).first()

            if existing_chat:
                return {"chat_id": existing_chat.id}

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
            avatar = db.query(UserPhoto).filter(
                UserPhoto.user_id == other_user_id,
                UserPhoto.is_avatar == True
            ).first()

            avatar_url = avatar.photo_url if avatar else None

            date_invitations = db.query(DateInvitations).filter(
                DateInvitations.recipient_id == current_user,
                DateInvitations.status == "pending"
            ).all()

            user2_data = UserInChat(
                user_id=user.id,
                first_name=user.first_name,
                user_age=age,
                status=user.status,
                avatar_url=avatar_url
            )

            # Получить последнее сообщение в чате
            last_message = db.query(Message).filter(
                Message.chat_id == chat.id,
                ((Message.deleted_for_user1.is_(False)) & (chat.user1_id == current_user)) |
                ((Message.deleted_for_user2.is_(False)) & (chat.user2_id == current_user))
            ).order_by(
                Message.created_at.desc()
            ).first()

            if last_message:
                message_type = last_message.message_type.name
                if message_type == 'voice':
                    last_message_content = 'Голосовое сообщение'
                elif message_type == 'image':
                    last_message_content = 'Изображение'
                elif message_type == 'text':
                    last_message_content = last_message.content
                else:
                    last_message_content = 'Неизвестный тип сообщения'

                last_message_status = status_mapping.get(last_message.status, None)
                last_message_sender_id = last_message.sender_id
            else:
                last_message_content = None
                last_message_status = None
                last_message_sender_id = None
                message_type = None

            # Получить количество непрочитанных сообщений
            unread_count = db.query(Message).filter(
                Message.chat_id == chat.id,
                Message.status != 'read',
                Message.sender_id != current_user,
                ((Message.deleted_for_user1.is_(False)) & (chat.user1_id == current_user)) |
                ((Message.deleted_for_user2.is_(False)) & (chat.user2_id == current_user))
            ).count()

            date_invitations_for_current_chat = [
                DateInvitationResponse(
                    sender_id=invite.sender_id,
                    status=invite.status
                ) for invite in date_invitations if invite.chat_id == chat.id]

            chat_response = ChatPersonResponse(
                chat_id=chat.id,
                user=user2_data,
                created_at=chat.created_at,
                last_message=last_message_content,
                unread_count=unread_count,
                last_message_status=last_message_status,
                last_message_sender_id=last_message_sender_id,
                last_message_type=message_type,
                date_invitations=date_invitations_for_current_chat
            )

            chat_responses.append(chat_response)

        return chat_responses


@router.get("/get_chat_id_by_user_id", response_model=ChatIdResponse, summary="Получить chat_id по recipient_id")
def get_chat_id_by_user_id(recipient_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        recipient = db.query(User).filter(User.id == recipient_id).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient user not found")

        chat = db.query(Chat).filter(
            ((Chat.user1_id == current_user_id) & (Chat.user2_id == recipient_id)) |
            ((Chat.user1_id == recipient_id) & (Chat.user2_id == current_user_id))
        ).first()

        if chat:
            return ChatIdResponse(chat_id=chat.id)
        else:
            raise HTTPException(status_code=404, detail="Chat not found")


@router.get("/{chat_id}", response_model=ChatDetailsResponse, summary="Получить детали чата")
def modified_get_chat_details(chat_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat.user1_id != current_user_id and chat.user2_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this chat")

        other_user_id = chat.user1_id if chat.user1_id != current_user_id else chat.user2_id
        user = db.query(User).filter(User.id == other_user_id).first()

        user_avatar = db.query(UserPhoto).filter(
            UserPhoto.user_id == other_user_id,
            UserPhoto.is_avatar == True
        ).first()

        today = date.today()
        age = today.year - user.date_of_birth.year - ((today.month, today.day) < (user.date_of_birth.month,
                                                                                  user.date_of_birth.day))

        chat_details = ChatDetailsResponse(
            user_id=user.id,
            first_name=user.first_name,
            user_age=age,
            avatar_url=user_avatar.photo_url if user_avatar else None,
            status=user.status if user.status is not None else None
        )

        return chat_details


@router.post("/update_fcm_token", summary="Обновить FCM-токен пользователя")
def update_fcm_token(request: AddTokenRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            current_user_id = get_user_id_from_token(access_token)

            existing_token = db.query(PushTokens).filter(
                PushTokens.user_id == current_user_id,
                PushTokens.token == request.token
            ).first()

            if existing_token:
                if not existing_token.active:
                    existing_token.active = True
                    db.commit()
                return {"message": "FCM-токен уже сохранен"}

            new_token = PushTokens(
                user_id=current_user_id,
                token=request.token,
                active=True
            )
            db.add(new_token)
            db.commit()
            return {"message": "FCM-токен обновлен"}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

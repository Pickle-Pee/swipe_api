from fastapi import FastAPI, Depends
import socketio

from common.models.communication_models import Chat, Message
from common.utils.auth_utils import get_user_id_from_token
from config import SECRET_KEY, SessionLocal

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio)

connected_users = {}


@sio.event
async def connect(sid, environ):
    access_token = environ.get('HTTP_AUTHORIZATION')  # Получаем токен из заголовков
    print(f"Received token: {access_token}")
    if not access_token:
        return False  # Закрыть соединение, если токена нет

    try:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        print(f"Authenticated user_id: {user_id}")  # Логирование аутентифицированного user_id
    except Exception as e:
        print(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        print(f"Failed token: {access_token[:10]}...")  # Логируем первые 10 символов токена для безопасности
        print(f"Environ: {environ}")  # Логируем дополнительные сведения о запросе (опционально)
        return False

    connected_users[user_id] = sid  # Сохраняем sid пользователя


@sio.event
async def send_message(sid, data):
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message_content = data.get('message')

    # Получаем ID чата между sender и receiver
    with SessionLocal() as db:
        chat = db.query(Chat).filter(
            ((Chat.user1_id == sender_id) & (Chat.user2_id == receiver_id)) |
            ((Chat.user1_id == receiver_id) & (Chat.user2_id == sender_id))
        ).first()

        if not chat:
            # Если чата нет, создаем новый (или вы можете выбросить ошибку)
            new_chat = Chat(user1_id=sender_id, user2_id=receiver_id)
            db.add(new_chat)
            db.commit()
            chat_id = new_chat.id
        else:
            chat_id = chat.id

        # Сохраняем сообщение в базе данных
        new_message = Message(chat_id=chat_id, sender_id=sender_id, content=message_content)
        db.add(new_message)
        db.commit()

    # Отправляем сообщение получателю, если он онлайн
    receiver_sid = connected_users.get(receiver_id)
    if receiver_sid:
        await sio.emit('new_message', {'message': message_content}, room=receiver_sid)


@sio.event
async def disconnect(sid):
    user_id = [k for k, v in connected_users.items() if v == sid][0]
    print(f"Disconnected: {user_id}")
    del connected_users[user_id]

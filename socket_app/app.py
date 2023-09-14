import os
import socketio
from common.models.communication_models import Chat, Message
from common.utils.auth_utils import get_user_id_from_token
from config import SECRET_KEY, SessionLocal

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio)

connected_users = {}


async def authenticate_user(access_token, environ):
    try:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        print(f"Authenticated user_id: {user_id}")
        return user_id
    except Exception as e:
        print(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        print(f"Failed token: {access_token[:10]}...")
        print(f"Environ: {environ}")
        return None


@sio.event
async def connect(sid, environ):
    access_token = environ.get('HTTP_AUTHORIZATION')
    print(f"Received token: {access_token}")
    if not access_token:
        return False

    user_id = await authenticate_user(access_token, environ)
    if user_id is None:
        return False

    connected_users[user_id] = sid


@sio.event
async def send_message(sid, data):
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message_content = data.get('message')

    with SessionLocal() as db:
        chat = db.query(Chat).filter(
            ((Chat.user1_id == sender_id) & (Chat.user2_id == receiver_id)) |
            ((Chat.user1_id == receiver_id) & (Chat.user2_id == sender_id))
        ).first()

        if not chat:
            new_chat = Chat(user1_id=sender_id, user2_id=receiver_id)
            db.add(new_chat)
            db.commit()
            chat_id = new_chat.id
        else:
            chat_id = chat.id

        new_message = Message(chat_id=chat_id, sender_id=sender_id, content=message_content)
        db.add(new_message)
        db.commit()

    receiver_sid = connected_users.get(receiver_id)
    if receiver_sid:
        await sio.emit('new_message', {'message': message_content}, room=receiver_sid)


@sio.event
async def disconnect(sid):
    user_id = [k for k, v in connected_users.items() if v == sid][0]
    print(f"Disconnected: {user_id}")
    del connected_users[user_id]


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)

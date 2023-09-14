import os
import socketio
from datetime import datetime
from common.models.communication_models import Chat, Message
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, SECRET_KEY
from urllib.parse import parse_qs

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*", logger=True, engineio_logger=True)
socket_app = socketio.ASGIApp(sio)

connected_users = {}


@sio.event
async def connect(sid, environ):
    query_string = environ.get('QUERY_STRING')
    parsed_params = parse_qs(query_string)
    access_token = parsed_params.get('token', [None])[0]

    # print(f"Received token: {access_token}")

    if not access_token:
        return False

    try:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        # print(f"Authenticated user_id: {user_id}")
    except Exception as e:
        print(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        return False

    connected_users[user_id] = {'sid': sid, 'user_id': user_id}
    # print(f"Connected users after new connection: {connected_users}")


@sio.event
async def get_messages(sid, data):
    print(f'---- Entering get_messages ----')

    chat_id = data.get('chat_id')

    print(f'Received data: {data}')
    print(f'chat_id: {chat_id}')
    print(f"get_messages: sid={sid}, connected_users={connected_users}")

    # Используем sid для поиска информации о пользователе
    user_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if sid not in [info['sid'] for info in connected_users.values()]:
        print(f"User with sid {sid} not found in connected_users")
    else:
        print(f"User with sid {sid} found in connected_users")

    if not user_info:
        print(f'User with sid {sid} not found')
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    # Получаем user_id из информации о пользователе
    user_id = user_info.get('user_id')

    if user_id in connected_users:
        print(f"User {user_id} reconnected with new sid: {sid}")
        connected_users[user_id]['sid'] = sid
    else:
        connected_users[user_id] = {'sid': sid, 'user_id': user_id}

    print(f'User info: {user_info}')

    with SessionLocal() as db:
        messages = db.query(Message).filter(Message.chat_id == chat_id).all()
        print(f'retrieved messages: {messages}')
        serialized_messages = []
        for message in messages:
            message_dict = message.as_dict()
            if 'created_at' in message_dict and isinstance(message_dict['created_at'], datetime):
                message_dict['created_at'] = message_dict['created_at'].isoformat()
            serialized_messages.append(message_dict)

        print(f'Messages: {serialized_messages}')

        await sio.emit('update_messages', {'messages': serialized_messages}, room=sid)

        print(f'---- Exiting get_messages ----')


@sio.event
async def send_message(sid, data):
    # print(f"Received send_message event with data: {data}")
    # print(f"Connected users at the time of message sending: {connected_users}")

    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message_content = data.get('message')

    sender_info = connected_users.get(sender_id)
    if not sender_info:
        # print("Sender info not found. Emitting completer with status 1.")
        await sio.emit('completer', {'sender_id': sender_id, 'status': 1, 'id': None})
        return

    with SessionLocal() as db:
        chat = db.query(Chat).filter(
            ((Chat.user1_id == sender_id) & (Chat.user2_id == receiver_id)) |
            ((Chat.user1_id == receiver_id) & (Chat.user2_id == sender_id))
        ).first()

        if not chat:
            # print("Chat not found. Creating a new chat.")
            new_chat = Chat(user1_id=sender_id, user2_id=receiver_id)
            db.add(new_chat)
            db.commit()
            chat_id = new_chat.id
        else:
            chat_id = chat.id

        # print(f"Adding new message to chat_id: {chat_id}")
        new_message = Message(chat_id=chat_id, sender_id=sender_id, content=message_content)
        db.add(new_message)
        db.commit()
        # print(f"Message committed to DB with id: {new_message.id}")
        message_id = new_message.id

    receiver_info = None
    for user_id, info in connected_users.items():
        if info.get('user_id') == receiver_id:
            receiver_info = info
            break

    if receiver_info:
        receiver_sid = receiver_info.get('sid')
        # print(f"Emitting new_message to receiver_sid: {receiver_sid}")
        await sio.emit(
            'new_message', {'id': message_id, 'msg': message_content, 'chat_id': chat_id}, room=receiver_sid)

    # print(f"Emitting completer with status 0 to sender_sid: {sid}")
    await sio.emit('completer', {'sender_id': sender_id, 'status': 0, 'id': message_id}, room=sid)


@sio.event
async def disconnect(sid):
    print(f"Disconnected: {sid}")
    user_id = next((user_id for user_id, info in connected_users.items() if info['sid'] == sid), None)
    if user_id:
        del connected_users[user_id]
        print(f"Removed user {user_id} with sid {sid} from connected_users")


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)

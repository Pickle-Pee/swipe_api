import json
import os
import socketio
from datetime import datetime
from common.models.communication_models import Chat, Message
from common.utils.auth_utils import get_user_id_from_token
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

    if not access_token:
        return False

    try:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
    except Exception as e:
        print(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        return False

    connected_users[user_id] = {'sid': sid, 'user_id': user_id}


@sio.event
async def get_messages(sid, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    user_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if not user_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info.get('user_id')

    if user_id in connected_users:
        connected_users[user_id]['sid'] = sid
    else:
        connected_users[user_id] = {'sid': sid, 'user_id': user_id}

    with SessionLocal() as db:
        messages = db.query(Message).filter(Message.chat_id == chat_id).all()
        serialized_messages = []

        for message in messages:
            message_dict = message.as_dict()

            if 'created_at' in message_dict and isinstance(message_dict['created_at'], datetime):
                message_dict['created_at'] = message_dict['created_at'].isoformat()
            serialized_messages.append(message_dict)

        await sio.emit('update_messages', {'messages': serialized_messages}, room=sid)


@sio.event
async def send_message(sid, data):

    if isinstance(data, str):
        data = json.loads(data)

    sender_id = data.get('sender_id')
    chat_id = data.get('chat_id')
    message_content = data.get('message')
    external_message_id = data.get('external_message_id')
    sender_info = connected_users.get(sender_id)

    if not sender_info:
        await sio.emit('completer', {'sender_id': sender_id, 'status': 1, 'id': None})
        return

    with SessionLocal() as db:
        new_message = Message(chat_id=chat_id, sender_id=sender_id, content=message_content)
        db.add(new_message)
        db.commit()
        message_id = new_message.id

    await sio.emit('completer', {
        'sender_id': sender_id,
        'status': 0,
        'id': message_id}, room=sid)


@sio.event
async def message_delivered(sid, data):
    message_id = data.get('message_id')
    with SessionLocal() as db:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.status = 'delivered'
            message.delivered_at = datetime.now()
            db.commit()
    await sio.emit('message_status', {'message_id': message_id, 'status': 'delivered'}, room=sid)


@sio.event
async def message_read(sid, data):
    message_id = data.get('message_id')
    with SessionLocal() as db:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.status = 'read'
            message.read_at = datetime.now()
            db.commit()
    await sio.emit('message_status', {'message_id': message_id, 'status': 'read'}, room=sid)


@sio.event
async def all_messages_read(sid, data):
    chat_id = data.get('chat_id')
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    with SessionLocal() as db:
        messages = db.query(Message).filter(Message.chat_id == chat_id).all()
        for message in messages:
            message.status = 'read'
            message.read_at = datetime.now()
        db.commit()
    receiver_info = connected_users.get(receiver_id)
    if receiver_info:
        receiver_sid = receiver_info.get('sid')
        await sio.emit('chat_status', {
            'chat_id': chat_id,
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'status': 'all_read'}, room=receiver_sid)


@sio.event
async def disconnect(sid):
    user_id = next((user_id for user_id, info in connected_users.items() if info['sid'] == sid), None)

    if user_id:
        del connected_users[user_id]
        print(f"Removed user {user_id} with sid {sid} from connected_users")


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)
